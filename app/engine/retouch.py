"""Local touch-ups, chosen by the user: remove a small object and smooth fabric.

Nothing here invents content from a model.  "Remove" fills the painted area from the pixels around it (diffusion
inpainting) and gives the fill the same grain as its surroundings; it works best on thin or small things such as a
broom handle, a cable or a socket, and smears on large objects.  "Smooth" flattens low-contrast creases in the painted
area (edge-preserving, colour and fine fabric grain kept).  Both work in tiles, so memory stays small on big photos.
"""
from __future__ import annotations

import cv2
import numpy as np

from .enhance import guided_self
from .retouch_ops import display_to_stored

TILE = 768
SMOOTH_STRENGTH = 0.65          # share of the crease contrast that is removed inside the painted area


def _stroke_mask(op: dict, W: int, H: int, orientation: int) -> tuple[np.ndarray, int, int]:
    """Mask (uint8 0/255) of one stroke on its own bounding box, plus the box's x0, y0."""
    L = max(W, H)
    rad = max(2, int(round(op["r"] * L)))
    pts = []
    for x, y in op["pts"]:
        sx, sy = display_to_stored(x, y, orientation)
        pts.append((sx * (W - 1), sy * (H - 1)))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    pad = rad + 2
    x0, y0 = max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad)
    x1, y1 = min(W, int(max(xs)) + pad + 1), min(H, int(max(ys)) + pad + 1)
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    q = [(int(round(x)) - x0, int(round(y)) - y0) for x, y in pts]
    for a, b in zip(q, q[1:] or [q[0]]):
        cv2.line(m, a, b, 255, 2 * rad + 1, cv2.LINE_8)
    for a in q:
        cv2.circle(m, a, rad, 255, -1, cv2.LINE_8)
    return m, x0, y0


def _tiles(w: int, h: int):
    for ty in range(0, h, TILE):
        for tx in range(0, w, TILE):
            yield tx, ty, min(w, tx + TILE), min(h, ty + TILE)


# ------------------------------------------------------------------------------ remove
def _remove_block(block: np.ndarray, mask: np.ndarray, rad: int) -> np.ndarray:
    """`block` with the masked pixels filled from their surroundings (returns a new array)."""
    grow = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * max(1, rad // 5) + 1,) * 2))
    filled = cv2.inpaint(block, grow, int(np.clip(rad * 0.7, 3, 12)), cv2.INPAINT_TELEA)
    # grain of the surroundings (a smooth fill next to a grainy photo looks pasted on)
    ring = cv2.dilate(grow, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rad + 9,) * 2)) & ~grow
    hp = block.astype(np.float32) - cv2.GaussianBlur(block, (0, 0), 1.6).astype(np.float32)
    sel = ring > 0
    sigma = 0.0
    if sel.sum() > 50:                                              # robust (MAD): edges in the ring must not make the fill noisy
        v = hp[sel]
        sigma = min(6.0, 1.4826 * float(np.median(np.abs(v - np.median(v)))))
    soft = cv2.GaussianBlur(grow.astype(np.float32) / 255.0, (0, 0), max(1.5, rad * 0.2))
    np.clip(soft, 0.0, 1.0, out=soft)
    if sigma > 0.2:
        rng = np.random.default_rng(1234 + block.shape[0] * 7 + block.shape[1])
        grain = rng.normal(0.0, sigma, block.shape[:2]).astype(np.float32)[:, :, None]
        filled = np.clip(filled.astype(np.float32) + grain * (grow[:, :, None] > 0), 0, 255)
    out = block.astype(np.float32) * (1.0 - soft[:, :, None]) + filled.astype(np.float32) * soft[:, :, None]
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------------------ smooth
def smooth_luma(y: np.ndarray, L: int, strength: float = SMOOTH_STRENGTH) -> np.ndarray:
    """Luma (float 0..1) with low-contrast creases flattened; strong edges and fine grain kept."""
    out = y
    for r_frac, eps in ((0.004, 0.004), (0.012, 0.008)):               # small creases, then larger dents
        r = max(3, int(r_frac * L))
        base = guided_self(out, r, eps)
        grain = out - cv2.GaussianBlur(out, (0, 0), 1.1)
        creases = out - base - grain
        out = base + grain + (1.0 - strength) * creases
    return out


def _smooth_block(block: np.ndarray, soft: np.ndarray, L: int, strength: float) -> np.ndarray:
    """Only the luma changes (colour is untouched, so no tints), and the painted area gets the photo's own grain back."""
    ycc = cv2.cvtColor(block, cv2.COLOR_BGR2YCrCb)
    y = ycc[:, :, 0].astype(np.float32) / 255.0
    ys = smooth_luma(y, L, strength)
    delta = (ys - y) * 255.0
    np.clip(delta, -14.0, 14.0, out=delta)                              # a touch-up, never a repaint
    hp = (y - cv2.GaussianBlur(y, (0, 0), 1.1)) * 255.0
    sigma = min(4.0, 1.4826 * float(np.median(np.abs(hp - np.median(hp)))))
    if sigma > 0.2:                                                    # smoothing also removes grain: put the same grain back
        rng = np.random.default_rng(99 + block.shape[0] * 3 + block.shape[1])
        delta += rng.normal(0.0, sigma * 0.6, y.shape).astype(np.float32) * np.clip(np.abs(delta) / 3.0, 0.0, 1.0)
    ycc[:, :, 0] = np.clip(ycc[:, :, 0].astype(np.float32) + delta * soft + 0.5, 0, 255).astype(np.uint8)
    return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)


# ------------------------------------------------------------------------------ driver
def apply_mask(img: np.ndarray, kind: str, mask: np.ndarray, x0: int, y0: int, rad: int, *, strength: float = SMOOTH_STRENGTH) -> None:
    """Apply one op in place, tile by tile.  `mask` is uint8 0/255 on the box starting at (x0, y0)."""
    H, W = img.shape[:2]
    L = max(W, H)
    mh, mw = mask.shape
    margin = (2 * rad + 24) if kind == "remove" else (3 * max(3, int(0.012 * L)) + 8)
    feather = max(1.5, rad * 0.25) if kind == "smooth" else 0
    for tx, ty, tx1, ty1 in _tiles(mw, mh):
        if not mask[ty:ty1, tx:tx1].any():
            continue
        ax0, ay0 = max(0, x0 + tx - margin), max(0, y0 + ty - margin)
        ax1, ay1 = min(W, x0 + tx1 + margin), min(H, y0 + ty1 + margin)
        block = np.ascontiguousarray(img[ay0:ay1, ax0:ax1])
        m = np.zeros(block.shape[:2], np.uint8)
        sx0, sy0 = max(x0 + tx, ax0), max(y0 + ty, ay0)               # the tile's own part of the mask, in block coords
        sx1, sy1 = min(x0 + tx1, ax1), min(y0 + ty1, ay1)
        # use the whole mask where it overlaps the block (not just the tile), so strokes crossing tile borders stay whole
        ox0, oy0 = max(ax0, x0), max(ay0, y0)
        ox1, oy1 = min(ax1, x0 + mw), min(ay1, y0 + mh)
        m[oy0 - ay0:oy1 - ay0, ox0 - ax0:ox1 - ax0] = mask[oy0 - y0:oy1 - y0, ox0 - x0:ox1 - x0]
        if kind == "remove":
            res = _remove_block(block, m, rad)
        else:
            soft = cv2.GaussianBlur(m.astype(np.float32) / 255.0, (0, 0), feather)
            np.clip(soft, 0.0, 1.0, out=soft)
            res = _smooth_block(block, soft, L, strength)
        # write back only this tile's own area (the margin was context)
        img[sy0:sy1, sx0:sx1] = res[sy0 - ay0:sy1 - ay0, sx0 - ax0:sx1 - ax0]


def apply(img: np.ndarray, ops: list[dict], orientation: int = 1) -> int:
    """Apply the user's strokes in order, in place, on the stored-layout BGR photo.  Returns how many were applied."""
    H, W = img.shape[:2]
    n = 0
    for op in ops:
        mask, x0, y0 = _stroke_mask(op, W, H, orientation)
        rad = max(2, int(round(op["r"] * max(W, H))))
        apply_mask(img, op["t"], mask, x0, y0, rad)
        n += 1
    return n
