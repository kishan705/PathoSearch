# PathoSearch v2: what was wrong in v1 and how it was fixed

Most important first. The numbers come from running the v1 code on synthetic slides
(`backend/tests/test_logic.py` checks the v2 behaviour on the same cases).

## Search quality

### 1. Only the top strip of each slide was indexed
v1 walked the slide row by row from the top-left and stopped at 1,000 tissue tiles. On a
12,800 × 12,800 slide that was 100% tissue, all 1,000 patches came from the **top 40%**; on a
real 50k × 50k slide it is closer to the top 5–10%. Most tissue was never searchable.
**Fix:** tissue is found on a thumbnail of the whole slide, and patches are sampled **evenly
across all of it** (`tissue.plan_cells` + `tissue.sample_evenly`). Test: 1,000 patches now span
the full height and width.

### 2. Black, empty areas were indexed as tissue
OpenSlide returns unscanned regions as transparent pixels. `.convert("RGB")` turns them
**black**, and the filter only rejected *bright* tiles (mean < 220 counted as tissue). In the
test slide, **32 of 48** "tissue" patches were pure black. Dust and marker ink passed too.
**Fix:** transparent areas are composited onto the slide's white background, and tissue is
detected by **colour saturation** (stain is colourful; glass and black are not), with very dark
pixels excluded and every patch double-checked at full resolution.

### 3. The similarity percentage was wrong
v1 used LanceDB's default L2 distance and showed `(1 - distance) × 100`. That isn't a
similarity: a true cosine of **0.80 showed as 60%** and **0.30 as −40%**.
**Fix:** searches use **cosine distance**, and the score shown is the cosine similarity.

### 4. Slides scanned at different magnifications weren't comparable
v1 always cut 256 px tiles at level 0, so a 40× tile covered a quarter of the tissue a 20× tile
did. **Fix:** every slide is sampled at **0.5 µm/pixel (20×)** using the file's own
microns-per-pixel (or objective power), so one patch is always 128 µm.

### 5. Results were neighbouring tiles of the same spot
The top 5 were often adjacent tiles of one region. **Fix:** 10× more candidates are fetched and
hits within two patches of an already chosen hit on the same slide are merged
(`ranking.diversify`). "Find similar" also leaves out the query spot itself.

## Reliability

### 6. The GPU was never used (and NVIDIA machines crashed)
`torch.device("mps" if torch.cuda.is_available() else "cpu")` is inverted: with CUDA present
it asked for Apple's `mps` device and crashed; on a Mac it used the CPU.
**Fix:** `cuda` → `mps` → `cpu`.

### 7. Uploads loaded the whole slide into memory
`await file.read()` read multi-GB WSIs into RAM, despite the README's "no RAM overflow".
**Fix:** uploads are streamed to disk in 8 MB chunks with a size limit.

### 8. Indexing froze the server
Cutting and embedding ran inside the upload request, in an `async` handler, so the server
couldn't answer anything else and the browser usually timed out. The README said it ran "in the
background"; it didn't. **Fix:** a background job queue with `queued → processing → done/failed`
status and progress, resumed automatically after a restart.

### 9. Results couldn't be traced back to a slide
Only a random UUID was stored per patch; the file name wasn't saved anywhere and there was no way
to list, view or delete slides. **Fix:** SQLite records for slides and patch positions, plus
endpoints for thumbnails, patch previews, coverage, re-index and delete.

### 10. Smaller issues
* Searching before any upload crashed (`open_table` on a missing table) → returns no results.
* A slide with no tissue returned "success" with 0 patches → now `failed` with a reason.
* Uploading the same file twice indexed it twice → SHA-256 duplicate detection.
* Uploaded files were never cleaned up → kept for previews, removed on delete.
* `requirements.txt` was missing `transformers` (needed by BiomedCLIP's text encoder) and the
  OpenSlide library; nothing was version-bounded → fixed, `openslide-bin` added.
* `db.table_names()` and `.metric()` are deprecated in newer LanceDB → compatible calls.
* The README promised features that didn't exist (background processing, no RAM overflow) → the
  README now describes what the code does.

## New

* **Text search** with BiomedCLIP's text encoder (prompt ensemble).
* **Find similar** from any spot on a slide.
* **Ordinary PNG/JPEG** images can be indexed (with or without OpenSlide installed).
* **React frontend:** search by text or image, slide library, upload with progress, and a slide
  viewer with coverage overlay and click-to-search.
* The original `/upload_slide/` and `/search_patch/` endpoints still work.
* **Live deployment** on Modal (GPU + Volume) with a Netlify frontend: an admin key protects
  uploading, re-indexing and deleting; databases are saved to the Volume after every change; the
  site stops polling when idle so an open tab doesn't keep the GPU running.
