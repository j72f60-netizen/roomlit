"""Retouch strokes: validation and coordinates (pure Python, so the web process can use it without OpenCV).

A stroke is {"t": "remove" | "smooth", "r": brush radius as a fraction of the photo's long edge,
"pts": [[x, y], ...]} with x, y in 0..1 measured on the photo *as it is displayed* (EXIF rotation applied), because
that is what the user paints on.  The engine maps them back to the stored pixel layout.
"""
from __future__ import annotations

KINDS = ("remove", "smooth")
MAX_STROKES = 60
MAX_POINTS = 600
MAX_TOTAL_POINTS = 6000
R_MIN, R_MAX = 0.002, 0.06


class BadStrokes(ValueError):
    pass


def clean_ops(raw) -> list[dict]:
    """Validate what the browser sent.  Raises BadStrokes; never trusts types or sizes."""
    if not isinstance(raw, list):
        raise BadStrokes("strokes must be a list")
    if len(raw) > MAX_STROKES:
        raise BadStrokes("too many strokes")
    out, total = [], 0
    for op in raw:
        if not isinstance(op, dict) or op.get("t") not in KINDS:
            raise BadStrokes("unknown stroke type")
        r, pts = op.get("r"), op.get("pts")
        if isinstance(r, bool) or not isinstance(r, (int, float)) or not (R_MIN <= float(r) <= R_MAX):
            raise BadStrokes("bad brush size")
        if not isinstance(pts, list) or not 1 <= len(pts) <= MAX_POINTS:
            raise BadStrokes("bad stroke")
        clean = []
        for p in pts:
            if (not isinstance(p, (list, tuple)) or len(p) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in p)):
                raise BadStrokes("bad point")
            x, y = float(p[0]), float(p[1])
            if not (-0.05 <= x <= 1.05 and -0.05 <= y <= 1.05):
                raise BadStrokes("point outside the photo")
            clean.append([round(min(1.0, max(0.0, x)), 5), round(min(1.0, max(0.0, y)), 5)])
        total += len(clean)
        if total > MAX_TOTAL_POINTS:
            raise BadStrokes("too many points")
        out.append({"t": op["t"], "r": round(float(r), 5), "pts": clean})
    return out


def display_to_stored(x: float, y: float, orientation: int) -> tuple[float, float]:
    """Normalised point on the displayed photo -> normalised point in the stored pixel layout (EXIF orientation 1..8)."""
    return {
        1: (x, y), 2: (1 - x, y), 3: (1 - x, 1 - y), 4: (x, 1 - y),
        5: (y, x), 6: (y, 1 - x), 7: (1 - y, 1 - x), 8: (1 - y, x),
    }.get(orientation, (x, y))
