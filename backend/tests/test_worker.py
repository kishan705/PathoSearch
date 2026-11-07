"""End-to-end test of the indexing worker with a stand-in model and vector store.

Uses the real SQLite database code, slide reading, tissue detection and job
logic; only BiomedCLIP and LanceDB are replaced (they need big downloads).
Run from the backend folder:   python tests/test_worker.py
"""
import os
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

tmp = tempfile.mkdtemp(prefix="pathosearch_test_")
os.environ["PATHOSEARCH_DATA"] = tmp

import config  # noqa: E402
import database as db  # noqa: E402
import model as model_mod  # noqa: E402
import vector_store  # noqa: E402
import worker  # noqa: E402

failures = 0


def check(name, cond, detail=""):
    global failures
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not cond:
        failures += 1


class FakeCLIP:
    def encode_images(self, images):
        return np.ones((len(images), 512), np.float32) / np.sqrt(512)


stored = []
model_mod.get_model = lambda timeout=None: FakeCLIP()
vector_store.add = lambda sid, vecs, coords, size: stored.append((sid, np.asarray(vecs).shape, list(coords), size)) or len(coords)
vector_store.delete_slide = lambda sid: None

config.ensure_dirs()
db.init()

# A 2048 x 1536 "slide" image: tissue on the left two thirds, glass on the right.
rng = np.random.default_rng(1)
arr = np.full((1536, 2048, 3), (244, 244, 246), np.uint8)
tissue = np.empty((1536, 1365, 3), np.uint8)
tissue[...] = (205, 120, 175)
tissue[rng.random((1536, 1365)) < 0.15] = (120, 70, 160)
arr[:, :1365] = tissue
path = os.path.join(config.SLIDE_DIR, "abc.png")
Image.fromarray(arr).save(path)

db.create_slide("abc", "demo.png", "hash1", path, os.path.getsize(path), max_patches=1000)
worker._process("abc")
s = db.get_slide("abc")

check("job finished with status 'done'", s["status"] == "done" and s["progress"] == 1, s["status"])
check("30 tissue patches indexed (5 columns x 6 rows), glass skipped",
      s["patches_indexed"] == 30, s["patches_indexed"])
check("vectors stored in batches with level-0 coordinates",
      sum(len(c) for _, _, c, _ in stored) == 30 and stored[0][1][1] == 512 and stored[0][3] == 256)
check("patch positions saved for the coverage overlay", len(db.patch_coords("abc")) == 30)
check("thumbnail written for the UI", os.path.exists(worker.thumb_path("abc")))
check("slide size and magnification recorded",
      (s["width"], s["height"]) == (2048, 1536) and s["magnification"].startswith("unknown"),
      (s["width"], s["height"], s["magnification"]))

# Duplicate detection
check("same file is recognised as a duplicate", db.find_by_hash("hash1")["id"] == "abc")

# A slide with no tissue fails with a clear message instead of 'success, 0 patches'
blank = os.path.join(config.SLIDE_DIR, "blank.png")
Image.new("RGB", (1024, 1024), (245, 245, 245)).save(blank)
db.create_slide("blank", "blank.png", "hash2", blank, 1, max_patches=1000)
worker._process("blank")
b = db.get_slide("blank")
check("blank slide -> 'failed' with a reason", b["status"] == "failed" and "No tissue" in (b["error"] or ""), b["error"])

# Re-indexing replaces old patch rows rather than adding duplicates
stored.clear()
worker._process("abc")
check("re-index does not duplicate patch rows", len(db.patch_coords("abc")) == 30)

# A job left 'processing' by a crash is resumed on start
db.update_slide("blank", status="processing")
check("unfinished jobs are found for resuming", [r["id"] for r in db.unfinished_slides()] == ["blank"])

print()
print("ALL PASSED" if failures == 0 else f"{failures} FAILED")
sys.exit(1 if failures else 0)
