"""PathoSearch API.

Run from the backend folder:
    python -m uvicorn main:app --port 8000
Docs: http://127.0.0.1:8000/docs
"""
import hashlib
import io
import os
import threading
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError

import config
import database as db
import model as model_mod
import ranking
import slide_io
import storage
import vector_store
import worker
from config import (
    ALLOWED_EXTENSIONS, CANDIDATE_MULTIPLIER, DEFAULT_MAX_PATCHES, DEFAULT_TOP_K,
    MAX_PATCHES_LIMIT, MAX_TOP_K, MAX_UPLOAD_GB, PATCH_SIZE, SLIDE_DIR,
)


@asynccontextmanager
async def lifespan(app):
    config.ensure_dirs()
    db.init()
    model_mod.start_loading()   # loads in the background; /api/health says when ready
    worker.start()              # resumes unfinished jobs
    yield


app = FastAPI(title="PathoSearch API", version="2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- helpers
def require_admin(x_admin_token: str = Header(None)):
    """Uploading, re-indexing and deleting need the admin key when one is configured."""
    if config.ADMIN_TOKEN and (x_admin_token or "").strip() != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Admin key required for uploading, re-indexing or deleting.")


def _slide_view(s):
    if s is None:
        return None
    view = {k: s.get(k) for k in (
        "id", "filename", "status", "progress", "error", "width", "height", "mpp",
        "magnification", "patch_size0", "tissue_cells", "patches_planned",
        "patches_indexed", "max_patches", "file_size", "created_at", "finished_at",
    )}
    view["thumbnail_url"] = (
        f"/api/slides/{s['id']}/thumbnail" if os.path.exists(worker.thumb_path(s["id"])) else None
    )
    return view


def _get_slide_or_404(slide_id):
    s = db.get_slide(slide_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Slide not found")
    return s


def _model():
    try:
        return model_mod.get_model(timeout=600)
    except (RuntimeError, TimeoutError) as e:
        raise HTTPException(status_code=503, detail=str(e))


# Small cache of open slides for patch previews (opening a big WSI for every image is slow)
_handles = OrderedDict()
_handles_lock = threading.Lock()


def _read_patch(s, x, y, size0):
    with _handles_lock:
        slide = _handles.pop(s["id"], None)
        if slide is None:
            slide = slide_io.open_any(s["file_path"])
        _handles[s["id"]] = slide
        while len(_handles) > 8:
            _, old = _handles.popitem(last=False)
            old.close()
        return slide_io.read_patch(slide, x, y, size0, PATCH_SIZE)


def _forget_handle(slide_id):
    with _handles_lock:
        h = _handles.pop(slide_id, None)
        if h is not None:
            h.close()


def _save_and_queue(file, max_patches):
    filename = os.path.basename(file.filename or "slide")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    max_patches = max(50, min(int(max_patches or DEFAULT_MAX_PATCHES), MAX_PATCHES_LIMIT))

    slide_id = uuid.uuid4().hex
    dest = os.path.join(SLIDE_DIR, slide_id + ext)   # our own name: no path tricks from the upload
    sha = hashlib.sha256()
    size, limit = 0, MAX_UPLOAD_GB * 1024 ** 3
    # Stream to disk in chunks (the original read the whole multi-GB file into RAM).
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = file.file.read(8 * 1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"File is larger than {MAX_UPLOAD_GB} GB")
                sha.update(chunk)
                out.write(chunk)
    except BaseException:
        if os.path.exists(dest):
            os.remove(dest)
        raise

    try:  # fail fast on files we can't read
        slide_io.open_any(dest).close()
    except Exception as e:
        os.remove(dest)
        raise HTTPException(status_code=400, detail=f"Could not open this file as a slide: {e}")

    digest = sha.hexdigest()
    existing = db.find_by_hash(digest)
    if existing:  # same file uploaded before: don't index it twice
        os.remove(dest)
        return {**_slide_view(existing), "duplicate": True}

    db.create_slide(slide_id, filename, digest, dest, size, max_patches)
    storage.persist()   # keep the record even if the server restarts mid-job
    worker.enqueue(slide_id)
    return {**_slide_view(db.get_slide(slide_id)), "duplicate": False}


def _search(vector, top_k, exclude=None):
    top_k = max(1, min(int(top_k), MAX_TOP_K))
    hits = vector_store.search(vector, top_k * CANDIDATE_MULTIPLIER)
    slides = db.slides_by_ids([h["slide_id"] for h in hits])
    hits = [h for h in hits if h["slide_id"] in slides]   # ignore deleted slides
    results = []
    for h in ranking.diversify(hits, top_k, exclude=exclude):
        s = slides[h["slide_id"]]
        results.append({
            "slide_id": h["slide_id"],
            "filename": s["filename"],
            "x": h["x"], "y": h["y"], "size": h["size"],
            "cosine": h["cosine"],
            "similarity": round(h["cosine"] * 100, 1),
            "patch_url": f"/api/slides/{h['slide_id']}/patch?x={h['x']}&y={h['y']}&size={h['size']}",
        })
    return results


def _load_query_image(file):
    data = file.file.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Query image must be under 50 MB")
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="That file is not an image (use PNG or JPEG)")


# ---------------------------------------------------------------------- status
@app.get("/api/health")
def health():
    return {
        **model_mod.status(),
        "openslide": slide_io.HAVE_OPENSLIDE,
        "read_only": bool(config.ADMIN_TOKEN),   # True: uploads/deletes need the admin key
        "slides": len(db.list_slides()),
        "patches": db.total_patches(),
    }


# ---------------------------------------------------------------------- slides
@app.post("/api/slides", dependencies=[Depends(require_admin)])
def upload_slide(file: UploadFile = File(...), max_patches: int = Form(DEFAULT_MAX_PATCHES)):
    """Upload a slide. Returns immediately; indexing runs in the background."""
    return _save_and_queue(file, max_patches)


@app.get("/api/slides")
def list_slides():
    return [_slide_view(s) for s in db.list_slides()]


@app.get("/api/slides/{slide_id}")
def get_slide(slide_id: str):
    return _slide_view(_get_slide_or_404(slide_id))


@app.delete("/api/slides/{slide_id}", dependencies=[Depends(require_admin)])
def delete_slide(slide_id: str):
    s = _get_slide_or_404(slide_id)
    if s["status"] == "processing":
        raise HTTPException(status_code=409, detail="This slide is being indexed. Delete it when it's done.")
    _forget_handle(slide_id)
    vector_store.delete_slide(slide_id)
    db.delete_slide(slide_id)
    for path in (s["file_path"], worker.thumb_path(slide_id)):
        if path and os.path.exists(path):
            os.remove(path)
    storage.persist()
    return {"deleted": slide_id}


@app.post("/api/slides/{slide_id}/reindex", dependencies=[Depends(require_admin)])
def reindex_slide(slide_id: str, max_patches: int = Form(None)):
    s = _get_slide_or_404(slide_id)
    if s["status"] in ("queued", "processing"):
        raise HTTPException(status_code=409, detail="Already queued or processing")
    fields = {"status": "queued", "progress": 0, "error": None}
    if max_patches:
        fields["max_patches"] = max(50, min(int(max_patches), MAX_PATCHES_LIMIT))
    db.update_slide(slide_id, **fields)
    storage.persist()
    worker.enqueue(slide_id)
    return _slide_view(db.get_slide(slide_id))


@app.get("/api/slides/{slide_id}/thumbnail")
def slide_thumbnail(slide_id: str):
    _get_slide_or_404(slide_id)
    path = worker.thumb_path(slide_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Thumbnail not ready yet")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/slides/{slide_id}/patches")
def slide_patches(slide_id: str):
    """Where the indexed patches are (level-0 pixels), for the coverage overlay."""
    s = _get_slide_or_404(slide_id)
    return {
        "width": s["width"], "height": s["height"], "patch_size0": s["patch_size0"],
        "coords": db.patch_coords(slide_id),
    }


@app.get("/api/slides/{slide_id}/patch")
def slide_patch(slide_id: str, x: int = Query(..., ge=0), y: int = Query(..., ge=0),
                size: int = Query(None, ge=16, le=16384)):
    """A 256x256 JPEG of the slide at (x, y) level-0 pixels."""
    s = _get_slide_or_404(slide_id)
    size0 = size or s["patch_size0"] or PATCH_SIZE
    if s["width"] and (x >= s["width"] or y >= s["height"]):
        raise HTTPException(status_code=400, detail="Coordinates are outside the slide")
    img = _read_patch(s, x, y, size0)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return Response(buf.getvalue(), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------- search
@app.post("/api/search/image")
def search_by_image(file: UploadFile = File(...), top_k: int = Form(DEFAULT_TOP_K)):
    """Find patches that look like the uploaded image (best: ~256 px crop at 20x)."""
    img = _load_query_image(file)
    vec = _model().encode_images([img])[0]
    return {"mode": "image", "results": _search(vec, top_k)}


@app.get("/api/search/text")
def search_by_text(q: str = Query(..., min_length=2, max_length=300), top_k: int = DEFAULT_TOP_K):
    """Find patches matching a description, e.g. 'mitotic figures' or 'adipose tissue'."""
    vec = _model().encode_text(q)
    return {"mode": "text", "query": q, "results": _search(vec, top_k)}


@app.get("/api/search/similar")
def search_similar(slide_id: str, x: int = Query(..., ge=0), y: int = Query(..., ge=0),
                   top_k: int = DEFAULT_TOP_K):
    """Find patches that look like the patch at (x, y) on a slide (excluding that spot)."""
    s = _get_slide_or_404(slide_id)
    size0 = s["patch_size0"] or PATCH_SIZE
    img = _read_patch(s, x, y, size0)
    vec = _model().encode_images([img])[0]
    return {"mode": "similar", "source": {"slide_id": slide_id, "x": x, "y": y, "size": size0},
            "results": _search(vec, top_k, exclude=(slide_id, x, y))}


# ------------------------------------------------- original endpoints (kept)
@app.post("/upload_slide/", dependencies=[Depends(require_admin)])
def upload_slide_legacy(file: UploadFile = File(...)):
    s = _save_and_queue(file, DEFAULT_MAX_PATCHES)
    return {"status": s["status"], "slide_id": s["id"], "duplicate": s.get("duplicate", False),
            "status_url": f"/api/slides/{s['id']}",
            "note": "Indexing runs in the background; poll status_url until status is 'done'."}


@app.post("/search_patch/")
def search_patch_legacy(file: UploadFile = File(...)):
    img = _load_query_image(file)
    vec = _model().encode_images([img])[0]
    return {"query_results": [
        {"slide_id": r["slide_id"], "filename": r["filename"], "x_coord": r["x"],
         "y_coord": r["y"], "similarity_score": r["similarity"]}
        for r in _search(vec, 5)
    ]}


# ------------------------------------------- serve the built frontend, if any
_dist = os.path.join(os.path.dirname(config.BASE_DIR), "frontend", "dist")
if os.path.isdir(_dist):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
