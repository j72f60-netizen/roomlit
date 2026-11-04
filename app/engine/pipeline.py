"""The two operations the server runs in its isolated worker process.

`analyze_file` runs when a photo arrives (validate, measure, make the "before"
preview).  `process_file` runs the enhancement and writes the edited photo and
its previews.  Both take and return plain picklable data.
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict

import cv2

from . import imageio, retouch
from .enhance import Analysis, analyze_bgr, enhance_inplace, group_white_balance, make_context
from .presets import get_preset

PREVIEW_EDGE = 1600
THUMB_EDGE = 420


def init_worker(max_pixels: int, threads: int) -> None:
    cv2.setNumThreads(threads)
    imageio.set_pixel_limit(max_pixels)


def _write_previews(preview_dir: str, item_id: int, img, orientation: int, kind: str) -> None:
    big = imageio.make_preview(img, orientation, PREVIEW_EDGE)
    imageio.save_preview(os.path.join(preview_dir, f"{item_id}_{kind}.jpg"), big, 86)
    thumb = imageio.make_preview(big, 1, THUMB_EDGE) if max(big.shape[:2]) > THUMB_EDGE else big
    imageio.save_preview(os.path.join(preview_dir, f"{item_id}_thumb.jpg"), thumb, 80)


def analyze_file(src: str, preview_dir: str, item_id: int, max_pixels: int) -> dict:
    t0 = time.perf_counter()
    meta = imageio.inspect(src, max_pixels)
    img = imageio.load_bgr(src, meta)
    an = analyze_bgr(img)
    _write_previews(preview_dir, item_id, img, meta.orientation, "before")
    return {
        "width": meta.width, "height": meta.height, "fmt": meta.fmt, "out_ext": meta.out_ext,
        "analysis": asdict(an), "seconds": round(time.perf_counter() - t0, 2),
    }


def group_params(analyses: list[dict]) -> dict:
    """Shared look for one apartment's photos (currently: the shared white-balance cast)."""
    objs = [Analysis(**{**a, "wb_gain": tuple(a["wb_gain"])}) for a in analyses]
    return {"wb": group_white_balance(objs)}


def process_file(src: str, dst: str, preview_dir: str, item_id: int, mode: str,
                 group_wb: tuple[float, float, float] | None, max_pixels: int, container: str | None = None,
                 strokes: list | None = None, enlarge_to: int = 0) -> dict:
    t0 = time.perf_counter()
    preset = get_preset(mode)
    meta = imageio.inspect(src, max_pixels)
    if container:                      # the edited file is written in the format its (unchanged) name promises
        meta.out_ext = container
    img = imageio.load_bgr(src, meta)
    h, w = img.shape[:2]
    if strokes:                        # the user's own touch-ups (remove / smooth) come first, so the edit treats them as the photo
        retouch.apply(img, strokes, meta.orientation)
    an = analyze_bgr(img)
    ctx = make_context(img, an, preset, group_wb)
    enhance_inplace(img, ctx)
    if img.shape[:2] != (h, w):  # pragma: no cover - guard: geometry must never change
        raise imageio.ImageError("Internal error: image size changed")
    if enlarge_to:                     # "enhance resolution": small photos get a bigger canvas, same proportions
        big = imageio.enlarge(img, enlarge_to)
        if big is not img:
            img = big
            h, w = img.shape[:2]
            meta.exif = imageio.exif_with_size(meta.exif, w, h)
    _write_previews(preview_dir, item_id, img, meta.orientation, "after")
    data = imageio.encode(img, meta)
    tmp = dst + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dst)
    return {
        "width": w, "height": h, "out_bytes": len(data),
        "exposure_gain": round(ctx.exposure_gain, 3),
        "wb": [round(g, 3) for g in ctx.wb_applied],
        "noise": round(an.noise, 4),
        "seconds": round(time.perf_counter() - t0, 2),
    }
