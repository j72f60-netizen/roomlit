"""Objective checks of the three modes on real sample photos (brightness, colour fidelity, structure)."""
import sys, os, glob, json
import numpy as np, cv2
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.engine import pipeline, imageio
from skimage.metrics import structural_similarity as ssim

pipeline.init_worker(80_000_000, 2)
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "samples", "**", "*.jpg"), recursive=True))
if len(sys.argv) > 2: files = [f for f in files if "living_big" not in f] if sys.argv[2] == "small" else files

def lab(bgr): return cv2.cvtColor(bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)
def small(p):
    im = cv2.imread(p); s = 800 / max(im.shape[:2]); return cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
rows = {m: [] for m in ("natural", "premium", "bright")}
for f in files:
    stem = os.path.splitext(os.path.basename(f))[0]
    a = small(f); la = lab(a); ya = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    for mode in rows:
        dst = os.path.join(OUT, f"{stem}_{mode}.jpg")
        r = pipeline.process_file(f, dst, OUT, 1, mode, None, 80_000_000)
        b = small(dst); lb = lab(b); yb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        d = {"img": stem, "mean": float(yb.mean() - ya.mean()), "p10": float(np.percentile(yb, 10) - np.percentile(ya, 10)),
             "p50": float(np.percentile(yb, 50) - np.percentile(ya, 50)),
             "clip_hi": float((yb >= 250).mean() - (ya >= 250).mean()) * 100, "clip_lo": float((yb <= 5).mean() - (ya <= 5).mean()) * 100}
        ca = np.hypot(la[..., 1], la[..., 2]); cb = np.hypot(lb[..., 1], lb[..., 2])
        m = (ca > 18) & (la[..., 0] > 15) & (la[..., 0] < 90)
        if m.sum() > 500:
            ha = np.degrees(np.arctan2(la[..., 2], la[..., 1])); hb = np.degrees(np.arctan2(lb[..., 2], lb[..., 1]))
            dh = np.abs((hb - ha + 180) % 360 - 180)[m]
            d["hue_med"] = float(np.median(dh)); d["hue_p95"] = float(np.percentile(dh, 95)); d["chroma_ratio"] = float(np.median(cb[m] / ca[m]))
        # structure: fit edited luma from original luma (global gain/offset) and compare local structure
        A = np.stack([ya.ravel(), np.ones(ya.size)], 1).astype(np.float32); coef = np.linalg.lstsq(A, yb.ravel().astype(np.float32), rcond=None)[0]
        fit = np.clip((A @ coef).reshape(ya.shape), 0, 255).astype(np.uint8)
        d["ssim"] = float(ssim(fit, yb, data_range=255))
        d["secs"] = r["seconds"]; d["dims_ok"] = (r["width"], r["height"]) == imageio.inspect(f, 80_000_000).__dict__.get("width") and True
        rows[mode].append(d)
for mode, ds in rows.items():
    g = lambda k: np.mean([x[k] for x in ds if k in x])
    print(f"{mode:8s} dMean={g('mean'):+5.1f} dP10={g('p10'):+5.1f} dP50={g('p50'):+5.1f} clipHi={g('clip_hi'):+5.2f}% clipLo={g('clip_lo'):+5.2f}% "
          f"hueMed={g('hue_med'):4.1f} hueP95={g('hue_p95'):5.1f} chromaRatio={g('chroma_ratio'):.3f} ssim={g('ssim'):.3f} (min {min(x['ssim'] for x in ds):.3f}) secs={g('secs'):.2f}")
json.dump(rows, open(os.path.join(OUT, "metrics.json"), "w"), indent=1)
