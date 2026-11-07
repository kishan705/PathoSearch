"""SQLite records for slides, their indexing jobs and patch positions.

The original only stored a random UUID per slide in the vector table, so a
search result could not be traced back to a file name, and there was no way
to list, inspect or delete slides.
"""
import sqlite3
import threading
import time
from contextlib import closing

from config import SQLITE_PATH

_lock = threading.Lock()

SLIDE_FIELDS = (
    "id", "filename", "sha256", "file_path", "file_size", "status", "progress", "error",
    "width", "height", "mpp", "magnification", "patch_size0", "tissue_cells",
    "patches_planned", "patches_indexed", "max_patches", "created_at", "finished_at",
)


def _connect():
    conn = sqlite3.connect(SQLITE_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with _lock, closing(_connect()) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slides (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                sha256 TEXT,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                status TEXT NOT NULL DEFAULT 'queued',
                progress REAL DEFAULT 0,
                error TEXT,
                width INTEGER, height INTEGER,
                mpp REAL, magnification TEXT,
                patch_size0 INTEGER,
                tissue_cells INTEGER,
                patches_planned INTEGER,
                patches_indexed INTEGER DEFAULT 0,
                max_patches INTEGER,
                created_at REAL,
                finished_at REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_slides_sha ON slides(sha256)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patches (
                slide_id TEXT NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_patches_slide ON patches(slide_id)")
        conn.commit()


def _one(sql, params=()):
    with closing(_connect()) as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def _all(sql, params=()):
    with closing(_connect()) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _write(sql, params=()):
    with _lock, closing(_connect()) as conn:
        conn.execute(sql, params)
        conn.commit()


def create_slide(slide_id, filename, sha256, file_path, file_size, max_patches):
    _write(
        "INSERT INTO slides (id, filename, sha256, file_path, file_size, status, progress, "
        "max_patches, created_at) VALUES (?, ?, ?, ?, ?, 'queued', 0, ?, ?)",
        (slide_id, filename, sha256, file_path, file_size, max_patches, time.time()),
    )


def update_slide(slide_id, **fields):
    bad = set(fields) - set(SLIDE_FIELDS)
    if bad:
        raise ValueError(f"Unknown fields: {bad}")
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    _write(f"UPDATE slides SET {cols} WHERE id = ?", (*fields.values(), slide_id))


def get_slide(slide_id):
    return _one("SELECT * FROM slides WHERE id = ?", (slide_id,))


def find_by_hash(sha256):
    return _one("SELECT * FROM slides WHERE sha256 = ? AND status != 'failed' ORDER BY created_at LIMIT 1", (sha256,))


def list_slides():
    return _all("SELECT * FROM slides ORDER BY created_at DESC")


def slides_by_ids(ids):
    ids = list(set(ids))
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    return {r["id"]: r for r in _all(f"SELECT * FROM slides WHERE id IN ({marks})", ids)}


def unfinished_slides():
    return _all("SELECT * FROM slides WHERE status IN ('queued', 'processing') ORDER BY created_at")


def delete_slide(slide_id):
    with _lock, closing(_connect()) as conn:
        conn.execute("DELETE FROM patches WHERE slide_id = ?", (slide_id,))
        conn.execute("DELETE FROM slides WHERE id = ?", (slide_id,))
        conn.commit()


def clear_patches(slide_id):
    _write("DELETE FROM patches WHERE slide_id = ?", (slide_id,))


def add_patches(slide_id, coords):
    with _lock, closing(_connect()) as conn:
        conn.executemany("INSERT INTO patches (slide_id, x, y) VALUES (?, ?, ?)",
                         [(slide_id, int(x), int(y)) for x, y in coords])
        conn.commit()


def patch_coords(slide_id):
    with closing(_connect()) as conn:
        return [(r[0], r[1]) for r in conn.execute(
            "SELECT x, y FROM patches WHERE slide_id = ? ORDER BY y, x", (slide_id,))]


def total_patches():
    row = _one("SELECT COUNT(*) AS n FROM patches")
    return row["n"] if row else 0
