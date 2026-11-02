"""Dev helper: run the organizer on a folder of photos and print what it decided."""
import sys, os, glob, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cv2
from app.engine import pipeline
from app.engine.organize.run import organize

folder = sys.argv[1]
files = sorted(glob.glob(os.path.join(folder, "**", "*.jpg"), recursive=True))
d = tempfile.mkdtemp(); pipeline.init_worker(80_000_000, 1)
items = []
for i, f in enumerate(files, 1):
    r = pipeline.analyze_file(f, d, i, 80_000_000)
    items.append({"id": i, "preview": f"{d}/{i}_before.jpg", "analysis": r["analysis"], "pixels": r["width"] * r["height"]})
import time; t = time.time()
res = organize([{"id": 0, "items": items}], "models")
print(f"organized {len(items)} photos in {time.time()-t:.1f}s, ml={res['ml']}")
name = {i + 1: os.path.relpath(f, folder) for i, f in enumerate(files)}
r = res["sets"][0]
for pos, i in enumerate(r["order"], 1):
    rm = r["rooms"][i]; print(f"{pos:2d}. {name[i]:42s} {rm['label']:9s} {rm['conf']:.2f} {'sure' if rm['sure'] else 'UNSURE'} grp={r['room_group'][i]} score={r['scores'][i]:.2f}" + (f" similar-to={r['similar'][i]}" if i in r['similar'] else ""))
for i, e in r["excluded"].items(): print(f"EXCLUDED {name[i]} -> duplicate of {name[e['dup_of']]} (inliers {e['inliers']}, d={e['d_mean']})")
