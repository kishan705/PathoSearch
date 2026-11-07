"""Save/restore of databases between local disk and durable storage (Modal Volume).

Run from the backend folder:   python tests/test_storage.py
"""
import os
import sqlite3
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import storage  # noqa: E402

failures = 0


def check(name, cond, detail=""):
    global failures
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not cond:
        failures += 1


root = tempfile.mkdtemp(prefix="pathosearch_storage_")
local = os.path.join(root, "local")
durable = os.path.join(root, "volume", "db")
os.makedirs(os.path.join(local, "lancedb", "pathology_patches_v2.lance", "data"))

# A live SQLite database in WAL mode with an uncommitted-to-main-file change
conn = sqlite3.connect(os.path.join(local, "pathosearch.db"))
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("CREATE TABLE slides (id TEXT, filename TEXT)")
conn.execute("INSERT INTO slides VALUES ('a', 'CMU-1.svs')")
conn.commit()
with open(os.path.join(local, "lancedb", "pathology_patches_v2.lance", "data", "part-0.lance"), "wb") as f:
    f.write(b"vectors")

commits = []
storage.sync_dir(local, durable, write_lock=threading.Lock(), commit=lambda: commits.append(1))
conn.close()

saved = sqlite3.connect(os.path.join(durable, "pathosearch.db"))
rows = saved.execute("SELECT filename FROM slides").fetchall()
saved.close()
check("SQLite copied consistently (even with WAL)", rows == [("CMU-1.svs",)], rows)
check("LanceDB files copied",
      os.path.exists(os.path.join(durable, "lancedb", "pathology_patches_v2.lance", "data", "part-0.lance")))
check("volume commit called once", commits == [1])

# New container: empty local disk, restore from durable storage
fresh = os.path.join(root, "fresh")
storage.restore_dir(durable, fresh)
again = sqlite3.connect(os.path.join(fresh, "pathosearch.db"))
check("restore brings the database back", again.execute("SELECT id FROM slides").fetchall() == [("a",)])
again.close()

# persist() is a no-op without a hook and never raises with a failing hook
storage.set_persist_hook(None)
storage.persist()
storage.set_persist_hook(lambda: 1 / 0)
storage.persist()
check("a failing save never breaks the request", True)

print()
print("ALL PASSED" if failures == 0 else f"{failures} FAILED")
sys.exit(1 if failures else 0)
