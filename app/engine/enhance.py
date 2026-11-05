"""Deterministic, non-generative photo enhancement.

Everything here is classical image processing (linear algebra on pixels).  No
pixel is ever invented: the output is the input with its tones, colour balance,
noise and local contrast adjusted.  Geometry is never touched.

Memory model
------------
The full image is held once, as uint8 (3 bytes per pixel).  It is enhanced in
horizontal strips, in place, so the float working set is bounded by the strip
size and not by the image size.  Global decisions (white balance, exposure and
the smooth tone map) are made once on a small ~960px copy and then sampled per
strip, so the result is identical to processing the whole frame at once.

All arrays are BGR (OpenCV order) in gamma-encoded 0..1 space.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .presets import Preset

# Rec.709 luma weights, BGR order.
W_B, W_G, W_R = 0.0722, 0.7152, 0.2126
_LUMA_M = np.array([[W_B, W_G, W_R]], dtype=np.float32)

WORK_EDGE = 960          # long edge of the analysis copy
STRIP_PIXELS = 400_000   # float working set is ~ (this * 12 bytes) per live 3-channel array
GAMMA = 2.2
DN_EPS_K = 2.2         # luma smoothing threshold, in units of the (gain-amplified) noise sigma
DN_BETA_GAIN = 1.3     # how much of the filtered result is mixed back in, relative to the preset strength
DN_RADIUS_BOOST = 1    # extra window radius when the photo is noisy


def luma(bgr: np.ndarray) -> np.ndarray:
    return cv2.transform(bgr, _LUMA_M)


def smoothstep(a: np.ndarray, e0: float, e1: float) -> np.ndarray:
    t = (a - e0) * (1.0 / (e1 - e0))
    np.clip(t, 0.0, 1.0, out=t)
    u = t * t
    t *= -2.0
    t += 3.0
    u *= t
    return u


# --------------------------------------------------------------------------
# filters
# --------------------------------------------------------------------------
def _box(a: np.ndarray, r: int) -> np.ndarray:
    k = 2 * r + 1
    return cv2.boxFilter(a, -1, (k, k), borderType=cv2.BORDER_REFLECT)


def guided_self(y: np.ndarray, r: int, eps) -> np.ndarray:
    """Edge-preserving smoothing of `y` guided by itself (He et al.)."""
    mean = _box(y, r)
    var = _box(y * y, r) - mean * mean
    np.maximum(var, 0.0, out=var)
    a = var / (var + eps)
    b = mean - a * mean
    return _box(a, r) * y + _box(b, r)


def guided_joint(guide: np.ndarray, targets: list[np.ndarray], r: int, eps) -> list[np.ndarray]:
    """Guided filtering of several targets with one luma guide (keeps colour edges aligned to luma edges)."""
    mean_g = _box(guide, r)
    var_g = _box(guide * guide, r) - mean_g * mean_g
    np.maximum(var_g, 0.0, out=var_g)
    denom = var_g + eps
    out = []
    for p in targets:
        mean_p = _box(p, r)
        cov = _box(guide * p, r) - mean_g * mean_p
        a = cov / denom
        b = mean_p - a * mean_g
        out.append(_box(a, r) * guide + _box(b, r))
    return out


def warp_rows(small: np.ndarray, row0: int, rows: int, width: int, full_h: int) -> np.ndarray:
    """Bilinearly sample a low-res map for full-res rows [row0, row0+rows)."""
    h, w = small.shape
    sy = h / full_h
    sx = w / width
    m = np.array([[sx, 0.0, 0.5 * sx - 0.5], [0.0, sy, (row0 + 0.5) * sy - 0.5]], dtype=np.float32)
    return cv2.warpAffine(
        small, m, (width, rows),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------
@dataclass
class Analysis:
    width: int
    height: int
    median: float                      # median luma of the well-exposed body of the scene
    clip_hi: float                     # fraction of near-white pixels (windows, lamps)
    clip_lo: float                     # fraction of near-black pixels
    wb_gain: tuple[float, float, float]  # measured BGR gains that would neutralise the cast (1,1,1 = none)
    wb_conf: float                     # 0..1 trust in that measurement
    noise: float                       # luma noise sigma, 0..1 units


def small_copy(bgr: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]
    s = WORK_EDGE / max(h, w)
    if s >= 1.0:
        return bgr.copy()
    return cv2.resize(bgr, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)


def estimate_noise(bgr: np.ndarray) -> float:
    """Robust luma noise sigma from flat-ish full-resolution crops (Haar HH, MAD)."""
    h, w = bgr.shape[:2]
    c = 192
    if h < c * 2 or w < c * 2:
        c = max(32, min(h, w) // 2)
    sigmas = []
    for fy in (0.2, 0.5, 0.8):
        for fx in (0.2, 0.5, 0.8):
            y0 = min(max(0, int(h * fy) - c // 2), h - c)
            x0 = min(max(0, int(w * fx) - c // 2), w - c)
            crop = bgr[y0:y0 + c, x0:x0 + c].astype(np.float32) * (1.0 / 255.0)
            g = luma(crop)
            d = (g[0::2, 0::2] - g[0::2, 1::2] - g[1::2, 0::2] + g[1::2, 1::2]) * 0.5
            sigmas.append(float(np.median(np.abs(d))) / 0.6745)
    return float(np.percentile(sigmas, 30))


def estimate_wb(small: np.ndarray) -> tuple[tuple[float, float, float], float]:
    """Estimate the illuminant from the brightest near-neutral surfaces (walls, ceilings, linen)."""
    y = luma(small)
    mx = small.max(axis=2)
    mn = small.min(axis=2)
    sat = (mx - mn) / (mx + 1e-6)
    valid = (y > 0.22) & (y < 0.93) & (mx < 0.985) & (sat < 0.22)
    n = int(valid.sum())
    if n < 0.02 * y.size:
        return (1.0, 1.0, 1.0), 0.0
    thr = np.percentile(y[valid], 55)
    sel = valid & (y >= thr)
    mean = small[sel].mean(axis=0)          # BGR
    lum = W_B * mean[0] + W_G * mean[1] + W_R * mean[2]
    gains = lum / np.maximum(mean, 1e-4)
    mag = float(np.max(np.abs(np.log(gains))))
    conf = min(1.0, n / (0.10 * y.size))
    if mag > 0.25:                          # a cast this strong is more likely a colourful scene than a lamp
        conf *= 0.5
    return (float(gains[0]), float(gains[1]), float(gains[2])), conf


def analyze_bgr(bgr: np.ndarray) -> Analysis:
    h, w = bgr.shape[:2]
    small = small_copy(bgr).astype(np.float32) * (1.0 / 255.0)
    y = luma(small)
    body = (y > 0.04) & (y < 0.93)
    if body.mean() < 0.05:
        body = np.ones_like(body)
    wb, conf = estimate_wb(small)
    return Analysis(
        width=w, height=h,
        median=float(np.median(y[body])),
        clip_hi=float((y > 0.98).mean()),
        clip_lo=float((y < 0.02).mean()),
        wb_gain=wb, wb_conf=conf,
        noise=estimate_noise(bgr),
    )


def group_white_balance(analyses: list[Analysis]) -> tuple[float, float, float] | None:
    """Confidence-weighted median of the measured casts for photos of one apartment."""
    pts = [(np.log(np.array(a.wb_gain)), a.wb_conf) for a in analyses if a.wb_conf > 0.2]
    if len(pts) < 2:
        return None
    logs = np.stack([p[0] for p in pts])
    wts = np.array([p[1] for p in pts])
    med = []
    for c in range(3):
        order = np.argsort(logs[:, c])
        cw = np.cumsum(wts[order])
        med.append(float(logs[order, c][np.searchsorted(cw, cw[-1] / 2.0)]))
    return tuple(float(np.exp(m)) for m in med)  # type: ignore[return-value]


# --------------------------------------------------------------------------
# tone model
# --------------------------------------------------------------------------
def _tone_gain(b: np.ndarray, p: Preset) -> np.ndarray:
    """Multiplicative gain as a function of the *smooth* base luminance (so local detail is preserved)."""
    b = np.clip(b, 0.0, 1.0)
    fade = smoothstep(b, 0.0, 0.10)                      # never lift true blacks into grey
    gs = 1.0 + p.shadow_lift * 0.9 * np.power(1.0 - b, 2.5) * fade
    t = smoothstep(b, 0.62, 1.0)
    gh = 1.0 - 0.30 * p.highlight_recover * t            # ease down bright areas (windows), never invent detail
    return (gs * gh).astype(np.float32)


def _curve(y: np.ndarray, p: Preset) -> np.ndarray:
    """Per-pixel luma curve: gentle contrast about the target median, then a soft highlight shoulder."""
    pivot = p.target_median
    y = y + (4.0 * p.contrast) * y * (1.0 - y) * (y - pivot) if p.contrast else y
    knee = p.knee if p.knee is not None else 0.90 - 0.06 * p.highlight_recover
    w = 1.0 - knee
    t = np.maximum(y - knee, 0.0)
    return y - t + w * np.tanh(t / w)


@dataclass
class Context:
    width: int
    height: int
    preset: Preset
    chan_gain: np.ndarray        # (3,) BGR = white balance * exposure
    gmap: np.ndarray             # low-res tone gain map
    cbase: np.ndarray            # low-res clarity base (post-curve luma, blurred)
    noise: float
    exposure_gain: float
    wb_applied: tuple[float, float, float]
    # derived, resolution dependent
    r_dn: int
    r_dn_c: int
    sharp_sigma: float


def make_context(bgr: np.ndarray, analysis: Analysis, preset: Preset,
                 group_wb: tuple[float, float, float] | None = None) -> Context:
    h, w = bgr.shape[:2]
    long_edge = max(h, w)
    small = small_copy(bgr).astype(np.float32) * (1.0 / 255.0)

    # --- white balance: own measurement, pulled toward the apartment's shared cast, then limited
    own = np.log(np.array(analysis.wb_gain, dtype=np.float64))
    conf = analysis.wb_conf
    if group_wb is not None:
        grp = np.log(np.array(group_wb, dtype=np.float64))
        # trust the photo's own measurement when it is reliable; lean on the apartment's shared cast when it is not
        w_own = min(1.0, max(0.0, (conf - 0.05) / 0.35))
        target = own * w_own + grp * (1.0 - w_own)
        conf = conf * w_own + 0.6 * (1.0 - w_own)
    else:
        target = own
    gains = np.exp(target * preset.wb_strength * conf)
    gains = np.clip(gains, 1.0 - preset.wb_max, 1.0 + preset.wb_max)
    gains = gains / (W_B * gains[0] + W_G * gains[1] + W_R * gains[2])   # keep brightness neutral
    wb = tuple(float(g) for g in gains)

    x = small * gains.astype(np.float32)
    y0 = luma(x)
    r = max(6, round(0.03 * max(small.shape[:2])))
    base0 = guided_self(y0, r, 0.02 ** 2)
    body = (y0 > 0.04) & (y0 < 0.93)
    if body.mean() < 0.05:
        body = np.ones_like(body)
    hl_w = 1.0 - preset.highlight_recover * smoothstep(base0, 0.55, 1.0)   # exposure change fades out in windows/lamps

    def total_gain(e: float) -> np.ndarray:
        ew = np.power(np.float32(e), hl_w)
        return ew * _tone_gain(base0 * ew, preset)

    def post_median(e: float) -> float:
        return float(np.median((y0 * total_gain(e))[body]))

    lo = 2.0 ** (-preset.max_ev / GAMMA)
    hi = 2.0 ** (preset.max_ev / GAMMA)
    if post_median(hi) <= preset.target_median:
        e = hi
    elif post_median(lo) >= preset.target_median:
        e = lo
    else:
        a, b = lo, hi
        for _ in range(14):
            mid = 0.5 * (a + b)
            if post_median(mid) < preset.target_median:
                a = mid
            else:
                b = mid
        e = 0.5 * (a + b)

    gmap = total_gain(e)
    gmap = cv2.GaussianBlur(gmap, (0, 0), 1.0)
    ytone = _curve(y0 * gmap, preset)
    sigma_w = max(1.5, 0.0035 * max(small.shape[:2]))
    cbase = cv2.GaussianBlur(ytone, (0, 0), sigma_w)

    chan_gain = gains.astype(np.float32)   # exposure lives in the smooth gain map (protects windows)
    scale = long_edge / 3000.0
    return Context(
        width=w, height=h, preset=preset, chan_gain=chan_gain,
        gmap=gmap.astype(np.float32), cbase=cbase.astype(np.float32),
        noise=analysis.noise, exposure_gain=float(e), wb_applied=wb,
        r_dn=max(1, round(2 * scale)), r_dn_c=max(2, round(4 * scale)),
        sharp_sigma=max(0.7, 0.9 * scale),
    )


# --------------------------------------------------------------------------
# strip enhancement
# --------------------------------------------------------------------------
def _enhance_block(block: np.ndarray, row0: int, ctx: Context) -> np.ndarray:
    """Enhance one strip.  `block` is uint8 BGR; returns float32 BGR clipped to 0..1."""
    p = ctx.preset
    rows, width = block.shape[:2]
    x = block.astype(np.float32)
    x *= (1.0 / 255.0)
    x *= ctx.chan_gain

    gain = warp_rows(ctx.gmap, row0, rows, width, ctx.height)
    x *= gain[..., None]
    Y = luma(x)

    # ---- noise reduction: more where the tone gain amplified the grain
    n = min(1.0, max(0.0, (ctx.noise - 0.0025) / 0.006))
    beta = min(0.92, p.denoise * n * DN_BETA_GAIN)
    if beta > 0.02:
        eps = (DN_EPS_K * ctx.noise * gain) ** 2
        Yf = guided_self(Y, ctx.r_dn + (DN_RADIUS_BOOST if n > 0.5 else 0), eps)
        Yn = Y + beta * (Yf - Y)
        cb = x[..., 0] - Y
        cr = x[..., 2] - Y
        cb_f, cr_f = guided_joint(Y, [cb, cr], ctx.r_dn_c, (3.0 * ctx.noise * gain) ** 2)
        cb = cb + min(1.0, beta * 1.25) * (cb_f - cb)
        cr = cr + min(1.0, beta * 1.25) * (cr_f - cr)
        x[..., 0] = Yn + cb
        x[..., 2] = Yn + cr
        x[..., 1] = (Yn - W_B * x[..., 0] - W_R * x[..., 2]) / W_G
        Y = Yn

    # ---- luma curve (contrast + highlight shoulder) applied as a ratio so colour is preserved
    Y2 = _curve(Y, p)
    s = Y2 / np.maximum(Y, 1e-4)
    np.minimum(s, 3.0, out=s)
    x *= s[..., None]
    Y = Y2

    # ---- local contrast ("clarity") and sharpening, luminance only
    delta = np.zeros_like(Y)
    if p.clarity > 0:
        cbase = warp_rows(ctx.cbase, row0, rows, width, ctx.height)
        detail = np.clip(Y - cbase, -0.06, 0.06)
        wmid = np.clip(4.0 * Y * (1.0 - Y), 0.25, 1.0)
        delta += (p.clarity * 0.75) * detail * wmid
    if p.sharpen > 0:
        Yc = Y + delta
        d = Yc - cv2.GaussianBlur(Yc, (0, 0), ctx.sharp_sigma)
        t = 1.4 * ctx.noise * np.maximum(gain, 1.0)          # never sharpen the grain itself
        d = np.sign(d) * np.maximum(np.abs(d) - t, 0.0)
        np.clip(d, -0.08, 0.08, out=d)
        d *= 0.3 + 0.7 * smoothstep(Y, 0.12, 0.40)            # lifted shadows carry mostly noise: sharpen them less
        delta += p.sharpen * d
    x += delta[..., None]
    np.clip(x, 0.0, 1.0, out=x)

    # ---- targeted, colour-safe adjustments
    if p.whites_clean > 0 or p.blue_lift > 0 or p.vibrance > 0 or p.saturation != 1.0:
        hsv = cv2.cvtColor(x, cv2.COLOR_BGR2HSV)
        H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        gsig = max(0.8, 1.2 * ctx.sharp_sigma)
        if p.blue_lift > 0:
            mh = smoothstep(H, 180.0, 200.0) * (1.0 - smoothstep(H, 250.0, 270.0))
            ms = smoothstep(S, 0.20, 0.40)
            mv = smoothstep(V, 0.08, 0.20) * (1.0 - smoothstep(V, 0.62, 0.82))
            m = cv2.GaussianBlur(mh * ms * mv, (0, 0), gsig)
            V *= 1.0 + 0.45 * p.blue_lift * m        # brighter, same hue and same saturation
        if p.whites_clean > 0:
            mw = (1.0 - smoothstep(S, 0.07, 0.20)) * smoothstep(V, 0.50, 0.68)
            mw = cv2.GaussianBlur(mw, (0, 0), gsig)
            S *= 1.0 - 0.65 * p.whites_clean * mw    # neutralise faint tints on white surfaces only
            V += 0.30 * p.whites_clean * mw * (1.0 - V) * 0.5
        if p.vibrance > 0:
            S *= 1.0 + p.vibrance * (1.0 - S)
        if p.saturation != 1.0:
            S *= p.saturation
        np.clip(S, 0.0, 1.0, out=S)
        np.clip(V, 0.0, 1.0, out=V)
        x = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    np.clip(x, 0.0, 1.0, out=x)
    return x


def enhance_inplace(img: np.ndarray, ctx: Context) -> None:
    """Enhance `img` (uint8 BGR, C-contiguous) in place, strip by strip."""
    H, W = img.shape[:2]
    halo = max(8, 2 * ctx.r_dn_c + 2, round(3 * ctx.sharp_sigma))
    rows = max(3 * halo, STRIP_PIXELS // W)
    carry: np.ndarray | None = None
    y = 0
    while y < H:
        y1 = min(H, y + rows)
        bot = min(H, y1 + halo)
        parts = [carry, img[y:bot]] if carry is not None else [img[y:bot]]
        block = np.concatenate(parts, axis=0) if len(parts) > 1 else img[y:bot].copy()
        top_rows = 0 if carry is None else carry.shape[0]
        out = _enhance_block(block, y - top_rows, ctx)
        core = out[top_rows:top_rows + (y1 - y)]
        # keep the untouched rows the next strip needs as its top halo
        carry = img[max(y, y1 - halo):y1].copy() if y1 < H else None
        core *= 255.0
        core += 0.5
        img[y:y1] = core          # float -> uint8 truncation after +0.5 == rounding
        del out, core, block
        y = y1
