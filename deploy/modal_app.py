"""Run the PathoSearch backend on Modal.

From the PathoSearch folder (once):
    python -m modal secret create pathosearch-secrets PATHOSEARCH_ADMIN_TOKEN=<a long random key>
Then, to deploy or update:
    python -m modal deploy deploy/modal_app.py

How it runs:
  * One container (max_containers=1) holds the API, the indexing worker and the
    model, exactly like running it on your computer. It answers many requests at
    once (@modal.concurrent) and shuts down after 10 idle minutes.
  * Slide files and thumbnails live on the Modal Volume "pathosearch-data".
  * SQLite and LanceDB run on the container's fast local disk and are copied to
    the Volume after every upload, finished job and delete (backend/storage.py),
    then restored when a new container starts.
  * BiomedCLIP is downloaded while building the image, so cold starts don't download it.
"""
from pathlib import Path

import modal

APP_NAME = "pathosearch"
GPU = "T4"            # set to None for CPU only: cheaper, but indexing is much slower
IDLE_SHUTDOWN_S = 600  # stop the container (and billing) after 10 idle minutes

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
MODEL = "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
VOLUME_DB_DIR = "/data/db"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(  # same as backend/requirements.txt
        "fastapi>=0.110", "uvicorn[standard]>=0.29", "python-multipart>=0.0.9",
        "numpy", "Pillow>=10.1", "openslide-python>=1.4", "openslide-bin",
        "lancedb>=0.20", "pyarrow>=14",
        "torch", "open_clip_torch>=2.24", "transformers>=4.40,<5",
    )
    .run_commands(
        "python -c \"import open_clip; "
        f"open_clip.create_model_from_pretrained('{MODEL}'); "
        f"open_clip.get_tokenizer('{MODEL}')\""
    )
    .env({
        "PATHOSEARCH_DATA": "/data",                    # slides + thumbnails (Volume)
        "PATHOSEARCH_DB_DIR": "/root/pathosearch-db",   # SQLite + LanceDB (local, synced)
        "PATHOSEARCH_CORS": "*",                        # the Netlify site calls this API
        "PATHOSEARCH_MAX_UPLOAD_GB": "2",
    })
    .add_local_dir(
        BACKEND_DIR,
        remote_path="/root/backend",
        ignore=["data", "data/**", "venv", "venv/**", "tests", "tests/**", "**/__pycache__/**"],
    )
)

volume = modal.Volume.from_name("pathosearch-data", create_if_missing=True)
secrets = [modal.Secret.from_name("pathosearch-secrets")]  # must exist before deploying

app = modal.App(APP_NAME, image=image)


@app.function(
    gpu=GPU,
    volumes={"/data": volume},
    secrets=secrets,
    max_containers=1,
    scaledown_window=IDLE_SHUTDOWN_S,
    timeout=3600,
)
@modal.concurrent(max_inputs=32)
@modal.asgi_app()
def web():
    import sys

    sys.path.insert(0, "/root/backend")

    import config
    import storage

    # Bring back the saved databases before anything opens them
    storage.restore_dir(VOLUME_DB_DIR, config.DB_DIR)

    import database
    import model
    import vector_store
    import worker
    from main import app as fastapi_app

    def save():
        storage.sync_dir(config.DB_DIR, VOLUME_DB_DIR,
                         write_lock=vector_store._write_lock, commit=volume.commit)

    storage.set_persist_hook(save)

    # Same start-up steps as main.py's lifespan (safe to run twice)
    config.ensure_dirs()
    database.init()
    model.start_loading()
    worker.start()
    return fastapi_app
