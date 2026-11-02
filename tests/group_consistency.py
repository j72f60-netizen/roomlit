"""Do photos of the same apartment end up closer in exposure and colour cast than they started?"""
import sys, os, glob
import numpy as np, cv2
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.engine import pipeline
pipeline.init_worker(80_000_000, 2)
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
def stats(path):
    im = cv2.imread(path); s = 600 / max(im.shape[:2]); im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    y = im @ np.array([0.0722, 0.7152, 0.2126], np.float32)
    mx, mn = im.max(2), im.min(2); sat = (mx - mn) / (mx + 1e-6)
    sel = (y > 0.3) & (y < 0.93) & (sat < 0.2)
    sel &= y >= np.percentile(y[sel], 60)
    m = im[sel].mean(0); return float(np.median(y)), float(np.log(m[2] / m[1])), float(np.log(m[0] / m[1]))   # luma median, log R/G, log B/G of whites
for group in ("Hotel Room A/Bedroom", "Hotel Room B"):
    files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "samples", group, "*.jpg")))
    an = [pipeline.analyze_file(f, OUT, i, 80_000_000)["analysis"] for i, f in enumerate(files)]
    gw = pipeline.group_params(an)["wb"]
    res = {"input": [stats(f) for f in files]}
    for label, g in (("solo", None), ("group", gw)):
        res[label] = []
        for i, f in enumerate(files):
            dst = os.path.join(OUT, f"{group.replace('/', '_').replace(' ', '')}_{label}_{i}.jpg")
            pipeline.process_file(f, dst, OUT, i, "premium", g, 80_000_000); res[label].append(stats(dst))
    print(group, "group WB gains (BGR):", [round(x, 3) for x in gw] if gw else None)
    for k, v in res.items():
        a = np.array(v); print(f"  {k:6s} luma spread (std)={a[:,0].std():.3f}  whites R/G spread={a[:,1].std():.4f}  B/G spread={a[:,2].std():.4f}")
