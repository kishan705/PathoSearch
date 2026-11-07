"""Opening slides and reading pixels, with OpenSlide when available.

Fixes vs. the original:
  * Unscanned/transparent areas are composited onto the slide's background
    colour (white) instead of turning black after .convert("RGB").
  * Ordinary images (PNG/JPEG/plain TIFF) also work, via OpenSlide's ImageSlide
    or a Pillow fallback when OpenSlide isn't installed.
  * Microns-per-pixel is read from the slide so every slide can be sampled at
    the same magnification.
"""
import math
import os

from PIL import Image

from config import MAX_IMAGE_PIXELS

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

try:  # OpenSlide is optional for ordinary images, required for real WSIs
    import openslide
    HAVE_OPENSLIDE = True
except Exception:  # ImportError, or the C library missing on Windows
    openslide = None
    HAVE_OPENSLIDE = False


class PILSlide:
    """Minimal OpenSlide-like wrapper for ordinary images when OpenSlide is unavailable."""

    def __init__(self, path):
        self._img = Image.open(path)
        self._img.load()
        self.dimensions = self._img.size
        self.level_count = 1
        self.level_dimensions = (self._img.size,)
        self.level_downsamples = (1.0,)
        self.properties = {}

    def get_best_level_for_downsample(self, downsample):
        return 0

    def read_region(self, location, level, size):
        x, y = location
        w, h = size
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.paste(self._img.crop((x, y, x + w, y + h)).convert("RGBA"), (0, 0))
        return out

    def get_thumbnail(self, size):
        thumb = self._img.convert("RGB")
        thumb.thumbnail(size, Image.Resampling.LANCZOS)
        return thumb

    def close(self):
        self._img.close()


def open_any(path):
    """Open a whole-slide image or an ordinary image."""
    if HAVE_OPENSLIDE:
        return openslide.open_slide(path)  # falls back to ImageSlide for PNG/JPEG
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        return PILSlide(path)
    raise RuntimeError(
        "OpenSlide is not installed, so whole-slide formats can't be read. "
        "Install it with:  pip install openslide-python openslide-bin"
    )


def background_rgb(slide):
    value = slide.properties.get("openslide.background-color", "ffffff") or "ffffff"
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def microns_per_pixel(slide):
    """Level-0 microns per pixel, or None if the file doesn't say."""
    props = slide.properties
    for key in ("openslide.mpp-x", "openslide.mpp-y"):
        try:
            value = float(props.get(key, ""))
            if value > 0:
                return value
        except ValueError:
            pass
    try:  # some files only store objective power: 40x ~ 0.25 um/px, 20x ~ 0.5 um/px
        power = float(props.get("openslide.objective-power", ""))
        if power > 0:
            return 10.0 / power
    except ValueError:
        pass
    return None


def flatten(region, bg=(255, 255, 255)):
    """RGBA -> RGB on the background colour (transparent areas become glass, not black)."""
    if region.mode != "RGBA":
        return region.convert("RGB")
    base = Image.new("RGB", region.size, bg)
    base.paste(region, mask=region.split()[3])
    return base


def read_patch(slide, x0, y0, size0, out_px):
    """Read a square of `size0` level-0 pixels at (x0, y0) and return it as out_px x out_px RGB."""
    downsample = size0 / out_px
    level = slide.get_best_level_for_downsample(max(downsample, 1.0))
    level_ds = slide.level_downsamples[level]
    read = max(1, int(math.ceil(size0 / level_ds)))
    region = slide.read_region((int(x0), int(y0)), level, (read, read))
    rgb = flatten(region, background_rgb(slide))
    if rgb.size != (out_px, out_px):
        rgb = rgb.resize((out_px, out_px), Image.Resampling.BILINEAR)
    return rgb


def thumbnail(slide, max_side):
    thumb = slide.get_thumbnail((max_side, max_side))
    return thumb.convert("RGB")
