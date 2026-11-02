"""Dev helper: run the engine on photos, write a contact sheet (original | natural | premium | bright)."""
import sys, os, time, resource
import numpy as np, cv2
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.engine import pipeline, imageio

out = sys.argv[1]; files = sys.argv[2:]
pipeline.init_worker(80_000_000, 2)
os.makedirs(out, exist_ok=True)
for f in files:
    stem = os.path.splitext(os.path.basename(f))[0]
    pv = os.path.join(out, "pv"); os.makedirs(pv, exist_ok=True)
    a = pipeline.analyze_file(f, pv, 1, 80_000_000)
    tiles = [cv2.imread(os.path.join(pv, "1_before.jpg"))]
    row = [f"{stem} {a['width']}x{a['height']} med={a['analysis']['median']:.2f} noise={a['analysis']['noise']:.4f}"]
    for mode in ("natural", "premium", "bright"):
        dst = os.path.join(out, f"{stem}_{mode}.jpg")
        r = pipeline.process_file(f, dst, pv, 1, mode, None, 80_000_000)
        im = cv2.imread(os.path.join(pv, "1_after.jpg")); tiles.append(im)
        row.append(f"{mode}: {r['seconds']}s e={r['exposure_gain']} wb={r['wb']}")
    h = 520
    tiles = [cv2.resize(t, (int(t.shape[1]*h/t.shape[0]), h), interpolation=cv2.INTER_AREA) for t in tiles]
    for t, lab in zip(tiles, ["original", "natural", "premium", "bright"]):
        cv2.putText(t, lab, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,255), 3, cv2.LINE_AA)
        cv2.putText(t, lab, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,0), 1, cv2.LINE_AA)
    sheet = np.concatenate([np.concatenate(tiles[:2], 1), np.concatenate(tiles[2:], 1)], 0) if tiles[0].shape == tiles[1].shape else np.concatenate(tiles, 1)
    cv2.imwrite(os.path.join(out, f"{stem}_sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(" | ".join(row))
print("peak RSS MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)
