"""Saving the databases somewhere durable.

On your own computer nothing is needed: everything is already on disk.

On Modal, containers start from a fresh disk. The slide files live directly on a
Modal Volume, while SQLite and LanceDB run on the container's fast local disk and
are copied to the Volume after every change (upload, finished job, delete).
`deploy/modal_app.py` installs that copy step with set_persist_hook().
"""
import os
import shutil
import sqlite3
import threading

_hook = None
_lock = threading.Lock()


def set_persist_hook(fn):
    global _hook
    _hook = fn


def persist():
    """Save databases to durable storage (no-op locally)."""
    if _hook is None:
        return
    with _lock:
        try:
            _hook()
        except Exception as e:  # never break a request because a backup failed
            print(f"persist failed: {type(e).__name__}: {e}")


def _copy_sqlite(src_path, dst_path):
    """Consistent copy of a live SQLite database (works with WAL)."""
    tmp = dst_path + ".tmp"
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    os.replace(tmp, dst_path)


def restore_dir(durable_dir, local_dir):
    """At startup: copy saved databases from durable storage to the local disk."""
    os.makedirs(local_dir, exist_ok=True)
    if os.path.isdir(durable_dir):
        shutil.copytree(durable_dir, local_dir, dirs_exist_ok=True)


def sync_dir(local_dir, durable_dir, write_lock=None, commit=None):
    """Copy SQLite + LanceDB from local_dir to durable_dir, then commit()."""
    os.makedirs(durable_dir, exist_ok=True)
    db_file = os.path.join(local_dir, "pathosearch.db")
    if os.path.exists(db_file):
        _copy_sqlite(db_file, os.path.join(durable_dir, "pathosearch.db"))
    lance = os.path.join(local_dir, "lancedb")
    if os.path.isdir(lance):
        lock = write_lock or threading.Lock()
        with lock:  # never copy a half-written vector table
            shutil.copytree(lance, os.path.join(durable_dir, "lancedb"), dirs_exist_ok=True)
    if commit is not None:
        commit()
