"""All PathoSearch settings in one place."""
import os

# ---------------------------------------------------------------------------
# Storage (everything lives under backend/data unless PATHOSEARCH_DATA is set)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("PATHOSEARCH_DATA", os.path.join(BASE_DIR, "data"))
SLIDE_DIR = os.path.join(DATA_DIR, "slides")        # uploaded slide files
THUMB_DIR = os.path.join(DATA_DIR, "thumbnails")    # small previews for the UI
# Databases can live elsewhere (on Modal: fast local disk, synced to the volume)
DB_DIR = os.environ.get("PATHOSEARCH_DB_DIR", DATA_DIR)
LANCEDB_DIR = os.path.join(DB_DIR, "lancedb")       # patch vectors
SQLITE_PATH = os.path.join(DB_DIR, "pathosearch.db")  # slide records + job status
TABLE_NAME = "pathology_patches_v2"                 # v2: new schema (old table is ignored)

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
MODEL_NAME = "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
EMBED_DIM = 512
TEXT_CONTEXT_LENGTH = 256
EMBED_BATCH_SIZE = 32
# Text queries are embedded with several phrasings and averaged (prompt ensemble).
TEXT_TEMPLATES = [
    "{}",
    "this is a photo of {}",
    "an H&E stained histopathology image of {}",
]

# ---------------------------------------------------------------------------
# Patch extraction
# ---------------------------------------------------------------------------
PATCH_SIZE = 256                 # pixels of every saved/embedded patch
TARGET_MPP = 0.5                 # microns per pixel = 20x magnification, for every slide
DEFAULT_MAX_PATCHES = 2000       # spread evenly over the WHOLE slide if there are more
MAX_PATCHES_LIMIT = 20000
THUMBNAIL_MAX = 2048             # tissue detection runs on a thumbnail this big
MIN_TISSUE_FRACTION = 0.5        # a grid cell needs this much tissue to be kept
MIN_SATURATION = 20              # 0-255; glass and black areas have low saturation
DARK_VALUE = 40                  # 0-255; pixels darker than this are artefacts, not tissue

ALLOWED_EXTENSIONS = {
    # whole-slide formats OpenSlide reads from a single file
    ".svs", ".tif", ".tiff", ".ndpi", ".scn", ".svslide", ".bif", ".vsi", ".dcm",
    # ordinary images (small demo images, crops)
    ".png", ".jpg", ".jpeg",
}
MAX_UPLOAD_GB = float(os.environ.get("PATHOSEARCH_MAX_UPLOAD_GB", "10"))

# If set, uploading, re-indexing and deleting need this key (header X-Admin-Token).
# Leave empty on your own computer; set it for a public deployment.
ADMIN_TOKEN = os.environ.get("PATHOSEARCH_ADMIN_TOKEN", "").strip()

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
DEFAULT_TOP_K = 12
MAX_TOP_K = 100
CANDIDATE_MULTIPLIER = 10        # fetch top_k x 10 candidates, then remove near-duplicates
NEIGHBOUR_DISTANCE = 2.0         # results closer than 2 patches on the same slide count as duplicates

# Allow very large ordinary images (Pillow refuses images above ~179M pixels by default)
MAX_IMAGE_PIXELS = 1_500_000_000

# Frontend dev server origins allowed to call the API directly
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "PATHOSEARCH_CORS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if o.strip()]


def ensure_dirs():
    for d in (DATA_DIR, SLIDE_DIR, THUMB_DIR, DB_DIR, LANCEDB_DIR):
        os.makedirs(d, exist_ok=True)
