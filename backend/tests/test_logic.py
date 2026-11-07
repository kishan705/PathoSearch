"""Logic tests that need only numpy + Pillow (no torch / OpenSlide / LanceDB).

Run from the backend folder:   python tests/test_logic.py
"""
import os
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import extractor  # noqa: E402
import ranking  # noqa: E402
import slide_io  # noqa: E402
import tissue  # noqa: E402

failures = 0


def check(name, cond, detail=""):
    global failures
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not cond:
        failures += 1


PINK = (205, 120, 175, 255)
PURPLE = (120, 70, 160, 255)
GLASS = (244, 244, 246, 255)
TRANSPARENT = (0, 0, 0, 0)


class FakeWSI(slide_io.PILSlide):
    """A PILSlide built from an in-memory RGBA image, optionally with an MPP value."""

    def __init__(self, rgba, mpp=None):
        self._img = rgba
        self.dimensions = rgba.size
        self.level_count = 1
        self.level_dimensions = (rgba.size,)
        self.level_downsamples = (1.0,)
        self.properties = {"openslide.mpp-x": str(mpp)} if mpp else {}

    def get_thumbnail(self, size):  # like OpenSlide: composite onto white
        thumb = slide_io.flatten(self._img.copy())
        thumb.thumbnail(size)
        return thumb


def textured(h, w, rng):
    """Pink/purple 'tissue' with nuclei-like noise."""
    arr = np.empty((h, w, 4), np.uint8)
    arr[...] = PINK
    dots = rng.random((h, w)) < 0.15
    arr[dots] = PURPLE
    return arr


rng = np.random.default_rng(0)

# --- 1. Whole-slide coverage: tissue everywhere, ask for 1000 patches -------------
W = H = 12800
big = Image.fromarray(textured(H, W, rng), "RGBA")
slide = FakeWSI(big)
plan = extractor.plan_slide(slide, max_patches=1000)
ys = [y for _, y in plan.cells]
xs = [x for x, _ in plan.cells]
check("coverage: 1000 patches spread over the whole height",
      len(plan.cells) == 1000 and min(ys) == 0 and max(ys) >= H - 2 * 256,
      f"y from {min(ys)} to {max(ys) + 256} of {H}")
check("coverage: and the whole width", min(xs) == 0 and max(xs) >= W - 2 * 256,
      f"x from {min(xs)} to {max(xs) + 256} of {W}")

# --- 2. Unscanned (transparent) + glass + tissue -------------------------------
W, H = 2048, 2048
arr = np.zeros((H, W, 4), np.uint8)
arr[...] = TRANSPARENT
arr[:, : W // 2] = textured(H, W // 2, rng)      # tissue: left half ...
arr[H // 2 :, : W // 2] = GLASS                  # ... except bottom-left is glass
slide = FakeWSI(Image.fromarray(arr, "RGBA"))
plan = extractor.plan_slide(slide, max_patches=1000)
patches = list(extractor.iter_patches(slide, plan))
black = [p for _, _, p in patches if np.asarray(p).mean() < 10]
inside = all(x < W // 2 and y < H // 2 for x, y, _ in patches)
check("no black patches from unscanned areas", len(black) == 0, f"{len(black)} black")
check("exactly the 16 real tissue patches, all inside the tissue",
      len(patches) == 16 and inside, f"{len(patches)} patches")

# --- 3. Dark artefact / pen mark is not tissue ----------------------------------
W, H = 1024, 1024
arr = np.zeros((H, W, 4), np.uint8)
arr[...] = GLASS
arr[:512, :512] = textured(512, 512, rng)
arr[512:, 512:] = (15, 15, 20, 255)              # black marker / dust
slide = FakeWSI(Image.fromarray(arr, "RGBA"))
plan = extractor.plan_slide(slide)
coords = sorted((x, y) for x, y, _ in extractor.iter_patches(slide, plan))
check("dark artefact ignored, tissue kept", coords == [(0, 0), (0, 256), (256, 0), (256, 256)], coords)

# --- 4. Same magnification for every slide --------------------------------------
W, H = 4096, 4096
img = Image.fromarray(textured(H, W, rng), "RGBA")
p40 = extractor.plan_slide(FakeWSI(img, mpp=0.25))   # 40x scan
p20 = extractor.plan_slide(FakeWSI(img, mpp=0.5))    # 20x scan
check("40x slide: one patch = 512 level-0 px (same 128 um as 20x)", p40.cell0 == 512, p40.cell0)
check("20x slide: one patch = 256 level-0 px", p20.cell0 == 256, p20.cell0)
patch = slide_io.read_patch(FakeWSI(img, mpp=0.25), 0, 0, 512, 256)
check("patches are always 256x256 RGB", patch.size == (256, 256) and patch.mode == "RGB")

# --- 5. Ordinary image file on disk (PNG) ---------------------------------------
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "crop.png")
    Image.fromarray(textured(900, 1300, rng)[..., :3]).save(path)
    patches, dims = extractor.extract_tissue_patches(path)
    check("ordinary PNG works and returns the original-style result",
          dims == (1300, 900) and len(patches) == 15 and patches[0]["image"].size == (256, 256),
          f"{len(patches)} patches, dims {dims}")
    small = os.path.join(d, "tiny.png")
    Image.fromarray(textured(120, 150, rng)[..., :3]).save(small)
    patches, _ = extractor.extract_tissue_patches(small)
    check("image smaller than one patch still gives 1 patch", len(patches) == 1, len(patches))

# --- 6. Ranking: cosine scores and near-duplicate removal ------------------------
hits = [  # same spot found 4 times + 2 other places
    {"slide_id": "A", "x": 1000, "y": 1000, "size": 256, "cosine": 0.95},
    {"slide_id": "A", "x": 1256, "y": 1000, "size": 256, "cosine": 0.94},
    {"slide_id": "A", "x": 1000, "y": 1256, "size": 256, "cosine": 0.93},
    {"slide_id": "A", "x": 1256, "y": 1256, "size": 256, "cosine": 0.92},
    {"slide_id": "A", "x": 9000, "y": 4000, "size": 256, "cosine": 0.90},
    {"slide_id": "B", "x": 1000, "y": 1000, "size": 256, "cosine": 0.89},
]
picked = ranking.diversify(hits, top_k=10)
check("neighbouring tiles of the same spot collapse to one result",
      [(h["slide_id"], h["x"]) for h in picked] == [("A", 1000), ("A", 9000), ("B", 1000)],
      [(h["slide_id"], h["x"], h["y"]) for h in picked])
picked = ranking.diversify(hits, top_k=10, exclude=("A", 1000, 1000))
check("'find similar' never returns the query spot itself",
      all(not (h["slide_id"] == "A" and abs(h["x"] - 1000) < 512 and abs(h["y"] - 1000) < 512) for h in picked),
      [(h["slide_id"], h["x"], h["y"]) for h in picked])
check("cosine from LanceDB cosine distance", ranking.cosine_from_distance(0.1) == 0.9)

print()
print("ALL PASSED" if failures == 0 else f"{failures} FAILED")
sys.exit(1 if failures else 0)
