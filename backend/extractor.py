"""Turn a slide into tissue patches at a fixed magnification."""
from dataclasses import dataclass, field

from config import DEFAULT_MAX_PATCHES, PATCH_SIZE, TARGET_MPP, THUMBNAIL_MAX
import slide_io
import tissue


@dataclass
class SlidePlan:
    width: int
    height: int
    mpp: float            # level-0 microns per pixel (None if unknown)
    cell0: int            # size of one patch in level-0 pixels
    sat_threshold: int
    thumb_size: tuple
    tissue_cells: int     # all tissue cells found
    cells: list = field(default_factory=list)   # the cells that will be embedded

    @property
    def magnification(self):
        if not self.mpp:
            return "unknown (native pixels)"
        return f"{10.0 / TARGET_MPP:.0f}x equivalent ({TARGET_MPP} µm/px)"


def plan_slide(slide, max_patches=DEFAULT_MAX_PATCHES, thumb=None):
    """Decide which patches to take, covering the whole slide."""
    width, height = slide.dimensions
    mpp = slide_io.microns_per_pixel(slide)
    # Same physical size for every slide: 256 px at 0.5 um/px = 128 um.
    cell0 = max(16, int(round(PATCH_SIZE * TARGET_MPP / mpp))) if mpp else PATCH_SIZE

    if thumb is None:
        thumb = slide_io.thumbnail(slide, THUMBNAIL_MAX)
    mask, sat_threshold = tissue.tissue_mask(thumb)
    all_cells = tissue.plan_cells(mask, width, height, cell0)
    if width < cell0 or height < cell0:
        cell0 = min(width, height)
    chosen = tissue.sample_evenly(all_cells, max_patches)
    return SlidePlan(width, height, mpp, cell0, sat_threshold, thumb.size, len(all_cells), chosen)


def iter_patches(slide, plan):
    """Yield (x0, y0, PIL patch) for planned cells that really contain tissue."""
    for x0, y0 in plan.cells:
        patch = slide_io.read_patch(slide, x0, y0, plan.cell0, PATCH_SIZE)
        if tissue.patch_is_tissue(patch, plan.sat_threshold):
            yield x0, y0, patch


def extract_tissue_patches(wsi_path, max_patches=DEFAULT_MAX_PATCHES):
    """Backwards-compatible helper: returns (patches, dimensions) like the original."""
    slide = slide_io.open_any(wsi_path)
    try:
        plan = plan_slide(slide, max_patches)
        patches = [
            {"image": img, "x": x, "y": y, "level": 0}
            for x, y, img in iter_patches(slide, plan)
        ]
        return patches, slide.dimensions
    finally:
        slide.close()
