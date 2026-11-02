"""Download the local room-detection model (OpenAI CLIP ViT-B/32 image encoder, MIT licence, int8 ONNX, ~89 MB).

Runs in a background thread at startup when the file is missing (and from scripts/fetch_models.py at build time).
SHA-256 verified, written atomically, retried.  Without the model the app still works, just without room labels.
"""
from __future__ import annotations

import hashlib
import logging
import os
import ssl
import time
import urllib.request

log = logging.getLogger("roomlit.model")

BASE = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/"
VISION = "vision_model_quantized.onnx"
FILES = {VISION: ("onnx/vision_model_quantized.onnx", "583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299")}
DEV_FILES = {"text_model_quantized.onnx": ("onnx/text_model_quantized.onnx", None), "tokenizer.json": ("tokenizer.json", None)}


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def present(model_dir: str) -> bool:
    return os.path.exists(os.path.join(model_dir, VISION))


def _fetch_one(dest_dir: str, name: str, remote: str, digest: str | None) -> bool:
    dst = os.path.join(dest_dir, name)
    if os.path.exists(dst) and (digest is None or _sha(dst) == digest):
        return True
    os.makedirs(dest_dir, exist_ok=True)
    for attempt in range(1, 5):
        tmp = dst + ".part"
        try:
            req = urllib.request.Request(BASE + remote, headers={"User-Agent": "roomlit/1.0"})
            with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as r, open(tmp, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            if digest and _sha(tmp) != digest:
                raise RuntimeError("checksum mismatch")
            os.replace(tmp, dst)
            log.info("room model ready (%s, %d KB)", name, os.path.getsize(dst) // 1024)
            return True
        except Exception as e:
            log.warning("model download attempt %d failed: %s", attempt, e)
            try:
                os.remove(tmp)
            except OSError:
                pass
            time.sleep(3 * attempt)
    return False


def fetch(dest_dir: str, dev: bool = False) -> bool:
    files = {**FILES, **(DEV_FILES if dev else {})}
    return all(_fetch_one(dest_dir, n, r, d) for n, (r, d) in files.items())
