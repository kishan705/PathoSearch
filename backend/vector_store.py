"""LanceDB storage for patch vectors.

Fixes vs. the original:
  * Searches use COSINE distance (the original used LanceDB's default L2 and then
    reported (1 - distance) x 100 as a percentage, which could even be negative).
  * Searching before any slide was indexed crashed; now it returns no results.
  * Rows can be deleted per slide (re-index / delete a slide).
  * Works across old and new LanceDB versions (table_names()/metric() were renamed).
"""
import threading

import numpy as np

from config import EMBED_DIM, LANCEDB_DIR, TABLE_NAME

_write_lock = threading.Lock()


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _db():
    import lancedb

    return lancedb.connect(LANCEDB_DIR)


def _schema():
    import pyarrow as pa

    return pa.schema([
        pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
        pa.field("slide_id", pa.string()),
        pa.field("x", pa.int64()),
        pa.field("y", pa.int64()),
        pa.field("size", pa.int32()),
    ])


def _open(db):
    try:
        return db.open_table(TABLE_NAME)
    except Exception:
        return None


def _open_or_create(db):
    tbl = _open(db)
    return tbl if tbl is not None else db.create_table(TABLE_NAME, schema=_schema())


def add(slide_id, vectors, coords, size):
    """vectors: float32 [N, 512]; coords: [(x, y), ...] level-0 pixels; size: patch size in level-0 px."""
    if len(coords) == 0:
        return 0
    vectors = np.asarray(vectors, dtype=np.float32)
    rows = [
        {"vector": vectors[i].tolist(), "slide_id": slide_id,
         "x": int(x), "y": int(y), "size": int(size)}
        for i, (x, y) in enumerate(coords)
    ]
    with _write_lock:
        _open_or_create(_db()).add(rows)
    return len(rows)


def delete_slide(slide_id):
    with _write_lock:
        tbl = _open(_db())
        if tbl is not None:
            tbl.delete(f"slide_id = {_quote(slide_id)}")


def search(vector, limit):
    """Nearest patches by cosine similarity: [{slide_id, x, y, size, cosine}]."""
    tbl = _open(_db())
    if tbl is None:
        return []
    q = tbl.search(np.asarray(vector, dtype=np.float32))
    q = q.distance_type("cosine") if hasattr(q, "distance_type") else q.metric("cosine")
    rows = q.select(["slide_id", "x", "y", "size"]).limit(int(limit)).to_list()
    return [
        {"slide_id": r["slide_id"], "x": int(r["x"]), "y": int(r["y"]),
         "size": int(r["size"]), "cosine": round(1.0 - float(r["_distance"]), 6)}
        for r in rows
    ]


def count():
    tbl = _open(_db())
    if tbl is None:
        return 0
    try:
        return int(tbl.count_rows())
    except Exception:
        return 0
