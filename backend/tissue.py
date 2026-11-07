"""Tissue detection and patch planning (numpy + Pillow only, easy to test).

Old approach: walk the full-resolution slide row by row from the top-left,
keep any 256x256 tile whose average brightness is < 220, stop at 1000 tiles.
  -> only the top strip of a big slide was indexed,
  -> black (unscanned) areas, pen marks and dark artefacts counted as "tissue",
  -> tens of thousands of full-resolution reads just to find background.

New approach:
  1. Make a small thumbnail of the whole slide.
  2. Mark tissue by colour SATURATION (stained tissue is colourful; glass is
     white/grey and unscanned areas are black, both have low saturation).
  3. Lay a grid of patch-sized cells over the slide and keep cells that are
     mostly tissue.
  4. If there are more cells than allowed, pick them evenly across the whole
     slide instead of taking the first N from the top.
"""
import numpy as np
from PIL import Image, ImageFilter

from config import DARK_VALUE, MIN_SATURATION, MIN_TISSUE_FRACTION


def otsu_threshold(values):
    """Otsu's threshold for uint8 values."""
    hist = np.bincount(values.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 0
    bins = np.arange(256)
    w0 = np.cumsum(hist)
    w1 = total - w0
    m0 = np.cumsum(hist * bins)
    mt = m0[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        mu0 = m0 / w0
        mu1 = (mt - m0) / w1
        between = w0 * w1 * (mu0 - mu1) ** 2
    between = np.nan_to_num(between)
    return int(np.argmax(between))


def saturation_threshold(thumb_rgb):
    """Pick a saturation cut-off between glass and tissue for this slide."""
    hsv = np.asarray(thumb_rgb.convert("HSV"))
    s = hsv[..., 1]
    t = otsu_threshold(s)
    # Clamp: never below MIN_SATURATION (glass noise), never above 50 (on slides
    # that are almost all tissue, Otsu would otherwise split pale pink from purple).
    return int(min(max(t, MIN_SATURATION), 50))


def tissue_pixels(rgb, sat_threshold):
    """Boolean array: True where a pixel looks like stained tissue."""
    hsv = np.asarray(rgb.convert("HSV"))
    return (hsv[..., 1] >= sat_threshold) & (hsv[..., 2] >= DARK_VALUE)


def tissue_mask(thumb_rgb, sat_threshold=None):
    """Clean tissue mask of a thumbnail. Returns (mask bool[h, w], threshold)."""
    if sat_threshold is None:
        sat_threshold = saturation_threshold(thumb_rgb)
    mask = tissue_pixels(thumb_rgb, sat_threshold)
    # Morphological opening + closing removes specks and fills tiny holes.
    img = Image.fromarray((mask * 255).astype(np.uint8))
    img = img.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    img = img.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    return np.asarray(img) > 127, sat_threshold


def plan_cells(mask, slide_w, slide_h, cell0, min_fraction=MIN_TISSUE_FRACTION):
    """Level-0 (x, y) of every grid cell whose area is mostly tissue, row by row."""
    if slide_w < cell0 or slide_h < cell0:
        # Image smaller than one patch: use the whole thing as a single patch.
        return [(0, 0)] if mask.mean() >= min_fraction * 0.5 else []

    mh, mw = mask.shape
    sx, sy = mw / slide_w, mh / slide_h
    # Integral image for O(1) tissue sums per cell
    integ = np.zeros((mh + 1, mw + 1), dtype=np.int64)
    integ[1:, 1:] = np.cumsum(np.cumsum(mask.astype(np.int64), axis=0), axis=1)

    xs = np.arange(0, slide_w - cell0 + 1, cell0)
    ys = np.arange(0, slide_h - cell0 + 1, cell0)
    x0 = np.clip(np.floor(xs * sx).astype(int), 0, mw - 1)
    x1 = np.clip(np.ceil((xs + cell0) * sx).astype(int), x0 + 1, mw)
    y0 = np.clip(np.floor(ys * sy).astype(int), 0, mh - 1)
    y1 = np.clip(np.ceil((ys + cell0) * sy).astype(int), y0 + 1, mh)

    Y0, X0 = np.meshgrid(y0, x0, indexing="ij")
    Y1, X1 = np.meshgrid(y1, x1, indexing="ij")
    sums = integ[Y1, X1] - integ[Y0, X1] - integ[Y1, X0] + integ[Y0, X0]
    areas = (Y1 - Y0) * (X1 - X0)
    frac = sums / np.maximum(areas, 1)

    rows, cols = np.nonzero(frac >= min_fraction)
    return [(int(xs[c]), int(ys[r])) for r, c in zip(rows, cols)]


def sample_evenly(cells, max_n):
    """Keep at most max_n cells, spread over the whole list (and so the whole slide)."""
    if max_n is None or len(cells) <= max_n:
        return list(cells)
    idx = np.unique(np.linspace(0, len(cells) - 1, max_n).round().astype(int))
    return [cells[i] for i in idx]


def patch_is_tissue(patch_rgb, sat_threshold, min_fraction=MIN_TISSUE_FRACTION * 0.8):
    """Full-resolution double check of a planned patch (thumbnails are coarse)."""
    return float(tissue_pixels(patch_rgb, sat_threshold).mean()) >= min_fraction
