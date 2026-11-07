"""Background indexing: one job at a time, with progress.

The original cut and embedded the whole slide inside the upload request, in an
`async` function, so the server froze (no other request could be answered) and
the browser usually timed out. Now /api/slides returns at once and this worker
does the slow part, updating `status` and `progress` as it goes. Jobs left
unfinished when the server stopped are picked up again at the next start.
"""
import os
import queue
import threading
import time
import traceback

from PIL import Image

import database as db
import extractor
import model as model_mod
import slide_io
import storage
import vector_store
from config import EMBED_BATCH_SIZE, THUMB_DIR, THUMBNAIL_MAX

_jobs = queue.Queue()
_started = threading.Event()
UI_THUMB_MAX = 1200


def thumb_path(slide_id):
    return os.path.join(THUMB_DIR, f"{slide_id}.jpg")


def enqueue(slide_id):
    _jobs.put(slide_id)


def start():
    if _started.is_set():
        return
    _started.set()
    for s in db.unfinished_slides():  # resume after a restart
        db.update_slide(s["id"], status="queued", progress=0)
        _jobs.put(s["id"])
    threading.Thread(target=_loop, name="indexer", daemon=True).start()


def _loop():
    while True:
        slide_id = _jobs.get()
        try:
            _process(slide_id)
        except Exception as e:
            traceback.print_exc()
            if db.get_slide(slide_id):
                db.update_slide(slide_id, status="failed", error=f"{type(e).__name__}: {e}",
                                finished_at=time.time())
        finally:
            storage.persist()   # save results (or the failure) to durable storage
            _jobs.task_done()


def _process(slide_id):
    rec = db.get_slide(slide_id)
    if rec is None:
        return  # deleted while waiting
    db.update_slide(slide_id, status="processing", progress=0, error=None)
    clip = model_mod.get_model()

    slide = slide_io.open_any(rec["file_path"])
    try:
        thumb = slide_io.thumbnail(slide, THUMBNAIL_MAX)
        ui_thumb = thumb.copy()
        ui_thumb.thumbnail((UI_THUMB_MAX, UI_THUMB_MAX), Image.Resampling.LANCZOS)
        ui_thumb.save(thumb_path(slide_id), quality=88)

        plan = extractor.plan_slide(slide, rec["max_patches"], thumb=thumb)
        db.update_slide(
            slide_id, width=plan.width, height=plan.height, mpp=plan.mpp,
            magnification=plan.magnification, patch_size0=plan.cell0,
            tissue_cells=plan.tissue_cells, patches_planned=len(plan.cells),
        )

        # A re-index starts clean, so old rows never linger.
        vector_store.delete_slide(slide_id)
        db.clear_patches(slide_id)

        done, indexed = 0, 0
        batch_imgs, batch_xy = [], []

        def flush():
            nonlocal indexed
            if not batch_imgs:
                return
            vecs = clip.encode_images(batch_imgs)
            vector_store.add(slide_id, vecs, batch_xy, plan.cell0)
            db.add_patches(slide_id, batch_xy)
            indexed += len(batch_xy)
            batch_imgs.clear()
            batch_xy.clear()

        for x0, y0 in plan.cells:
            patch = slide_io.read_patch(slide, x0, y0, plan.cell0, extractor.PATCH_SIZE)
            done += 1
            if extractor.tissue.patch_is_tissue(patch, plan.sat_threshold):
                batch_imgs.append(patch)
                batch_xy.append((x0, y0))
            if len(batch_imgs) >= EMBED_BATCH_SIZE:
                flush()
                db.update_slide(slide_id, progress=round(done / max(len(plan.cells), 1), 4),
                                patches_indexed=indexed)
        flush()
    finally:
        slide.close()

    if indexed == 0:
        db.update_slide(slide_id, status="failed", progress=1, patches_indexed=0,
                        error="No tissue found on this slide.", finished_at=time.time())
        return
    db.update_slide(slide_id, status="done", progress=1, patches_indexed=indexed,
                    finished_at=time.time())
    print(f"Indexed {indexed} patches for {rec['filename']} ({slide_id})")
