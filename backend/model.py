"""BiomedCLIP, loaded once in the background when the server starts.

Fixes vs. the original indexer.py:
  * Device choice was inverted: torch.device("mps" if torch.cuda.is_available() ...)
    crashed on NVIDIA machines and never used Apple GPUs. Now: cuda -> mps -> cpu.
  * The model loaded at import time; now it loads in a background thread so the
    API starts immediately and /api/health reports when it's ready.
  * Text search: BiomedCLIP also has a text encoder, so you can search with words.
"""
import os
import threading

import numpy as np

from config import EMBED_BATCH_SIZE, MODEL_NAME, TEXT_CONTEXT_LENGTH, TEXT_TEMPLATES

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # Apple GPUs: CPU fallback for missing ops

_state = {"model": None, "error": None}
_ready = threading.Event()
_load_lock = threading.Lock()


def pick_device():
    import torch

    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


class BiomedCLIP:
    def __init__(self):
        import open_clip
        import torch

        self.torch = torch
        self.device = pick_device()
        print(f"Loading BiomedCLIP on {self.device} (first run downloads ~800 MB)...")
        if hasattr(open_clip, "create_model_from_pretrained"):
            model, preprocess = open_clip.create_model_from_pretrained(MODEL_NAME)
        else:  # older open_clip
            model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME)
        self.model = model.to(self.device).eval()
        self.preprocess = preprocess
        self.tokenizer = open_clip.get_tokenizer(MODEL_NAME)
        self._lock = threading.Lock()  # indexing worker and searches share one model
        print("BiomedCLIP ready.")

    def _normalize(self, feats):
        feats = feats.float()
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
        return feats.cpu().numpy().astype(np.float32)

    def encode_images(self, images):
        out = []
        torch = self.torch
        for i in range(0, len(images), EMBED_BATCH_SIZE):
            batch = torch.stack([self.preprocess(img.convert("RGB")) for img in images[i:i + EMBED_BATCH_SIZE]])
            with self._lock, torch.inference_mode():
                out.append(self._normalize(self.model.encode_image(batch.to(self.device))))
        return np.concatenate(out) if out else np.zeros((0, 512), np.float32)

    def encode_text(self, query):
        """Average of several phrasings of the query, as one normalised vector."""
        torch = self.torch
        q = " ".join(query.strip().split())
        texts = [t.format(q) for t in TEXT_TEMPLATES]
        tokens = self.tokenizer(texts, context_length=TEXT_CONTEXT_LENGTH).to(self.device)
        with self._lock, torch.inference_mode():
            feats = self._normalize(self.model.encode_text(tokens))
        v = feats.mean(axis=0)
        return (v / np.linalg.norm(v)).astype(np.float32)


def _load():
    try:
        _state["model"] = BiomedCLIP()
    except Exception as e:  # keep the API up and report the problem
        import traceback

        traceback.print_exc()
        _state["error"] = f"{type(e).__name__}: {e}"
    finally:
        _ready.set()


def start_loading():
    with _load_lock:
        if not _ready.is_set() and not getattr(start_loading, "started", False):
            start_loading.started = True
            threading.Thread(target=_load, name="model-loader", daemon=True).start()


def get_model(timeout=None):
    """Block until the model is loaded. Raises RuntimeError if loading failed."""
    start_loading()
    if not _ready.wait(timeout):
        raise TimeoutError("The AI model is still loading. Try again in a moment.")
    if _state["model"] is None:
        raise RuntimeError(f"The AI model failed to load: {_state['error']}")
    return _state["model"]


def status():
    m = _state["model"]
    return {
        "model_ready": m is not None,
        "model_error": _state["error"],
        "device": m.device if m else None,
    }
