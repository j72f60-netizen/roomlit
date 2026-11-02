"""Per-photo measurements and pair comparison used for duplicate detection.

Duplicates are found by *geometry*, not by file name, size or brightness: two photos are the same shot when
local features (ORB) match under a near-identity transform.  A photo of the same room from a different spot
matches with a large displacement (or not at all) and is therefore kept.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

WORK = 800                      # long edge used for feature matching
_ORB = None


def _orb():
    global _orb_obj
    try:
        return _orb_obj
    except NameError:
        _orb_obj = cv2.ORB_create(nfeatures=900, scaleFactor=1.2, nlevels=8, fastThreshold=10)
        return _orb_obj


@dataclass
class Feat:
    w: int                       # preview size (display orientation)
    h: int
    ww: int                      # working size
    wh: int
    kp: np.ndarray               # (N,2) float32, working-size pixels
    des: np.ndarray | None       # (N,32) uint8
    thumb: np.ndarray            # 64x48 equalised gray, float32 standardised (for NCC)
    sharp: float                 # Laplacian variance at 1000px (log-scaled later)
    quality: float               # 0..1 capture quality (sharpness, exposure, noise, resolution)


def _quality(sharp: float, median: float, clip_hi: float, clip_lo: float, noise: float, pixels: int) -> float:
    s = min(1.0, np.log1p(sharp) / np.log1p(300.0))
    base = 1.0 - min(1.0, abs(median - 0.48) / 0.40)
    pen = min(0.5, 4.0 * max(0.0, clip_hi - 0.02)) + min(0.4, 6.0 * max(0.0, clip_lo - 0.03))
    e = float(np.clip(base - pen, 0.0, 1.0))
    n = 1.0 - min(1.0, noise / 0.02)
    r = min(1.0, float(np.sqrt(pixels / 12e6)))
    return float(0.40 * s + 0.20 * e + 0.10 * n + 0.20 * r + 0.10 * 0.5)   # last term: placeholder for appeal, filled later


def extract(bgr: np.ndarray, analysis: dict, full_pixels: int) -> Feat:
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    s = WORK / max(h, w)
    g = cv2.resize(gray, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA) if s < 1 else gray.copy()
    ww, wh = g.shape[1], g.shape[0]
    eq = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(g)
    kp, des = _orb().detectAndCompute(eq, None)
    pts = np.array([k.pt for k in kp], dtype=np.float32) if kp else np.zeros((0, 2), np.float32)
    t = cv2.equalizeHist(cv2.resize(g, (64, 48), interpolation=cv2.INTER_AREA)).astype(np.float32)
    t -= t.mean()
    t /= (t.std() + 1e-6)
    k = 1000.0 / max(h, w)
    g1 = cv2.resize(gray, (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA)
    sharp = float(cv2.Laplacian(g1, cv2.CV_32F).var())
    q = _quality(sharp, analysis.get("median", 0.5), analysis.get("clip_hi", 0.0), analysis.get("clip_lo", 0.0),
                 analysis.get("noise", 0.0), full_pixels)
    return Feat(w, h, ww, wh, pts, des, t, sharp, q)


@dataclass
class Pair:
    ncc: float
    n_good: int
    n_in: int
    ratio: float
    d_mean: float                # mean displacement of a point grid under the fitted transform, fraction of the diagonal
    d_max: float
    aspect_ok: bool


_BF = None


def compare(a: Feat, b: Feat) -> Pair:
    aspect_ok = abs((a.w / a.h) / (b.w / b.h) - 1.0) < 0.03
    ncc = float((a.thumb * b.thumb).mean()) if aspect_ok else 0.0
    n_good = n_in = 0
    d_mean = d_max = 9.0
    if a.des is not None and b.des is not None and len(a.des) >= 15 and len(b.des) >= 15:
        global _BF
        if _BF is None:
            _BF = cv2.BFMatcher(cv2.NORM_HAMMING)
        m = _BF.knnMatch(a.des, b.des, k=2)
        good = [x[0] for x in m if len(x) == 2 and x[0].distance < 0.78 * x[1].distance]
        n_good = len(good)
        if n_good >= 12:
            src = a.kp[[g.queryIdx for g in good]]
            dst = b.kp[[g.trainIdx for g in good]]
            # bring b into a's frame when the working sizes differ slightly
            dst = dst * np.array([a.ww / b.ww, a.wh / b.wh], dtype=np.float32)
            H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
            if H is not None and mask is not None:
                n_in = int(mask.sum())
                gx, gy = np.meshgrid(np.linspace(0.1, 0.9, 5) * a.ww, np.linspace(0.1, 0.9, 5) * a.wh)
                P = np.stack([gx.ravel(), gy.ravel(), np.ones(25)], 0).astype(np.float64)
                Q = H @ P
                with np.errstate(all="ignore"):
                    Q = Q[:2] / Q[2:3]
                disp = np.hypot(Q[0] - P[0], Q[1] - P[1]) / np.hypot(a.ww, a.wh)
                if np.all(np.isfinite(disp)):
                    d_mean, d_max = float(disp.mean()), float(disp.max())
    return Pair(ncc, n_good, n_in, (n_in / n_good) if n_good else 0.0, d_mean, d_max, aspect_ok)
