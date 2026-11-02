import sys, os, glob, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cv2, numpy as np
from app.engine.organize import features as F

def prev(path):
    im = cv2.imread(path); s = 1600 / max(im.shape[:2]); return cv2.resize(im, None, fx=min(1, s), fy=min(1, s), interpolation=cv2.INTER_AREA)
AN = {"median": 0.5, "clip_hi": 0.0, "clip_lo": 0.0, "noise": 0.005}
def feat(im): return F.extract(im, AN, im.shape[0] * im.shape[1])
def show(label, p): print(f"{label:34s} ncc={p.ncc:5.2f} good={p.n_good:4d} inl={p.n_in:4d} ratio={p.ratio:4.2f} d_mean={p.d_mean:6.3f} d_max={p.d_max:6.3f}")

src = prev("tests/samples/Hotel Room A/Bedroom/bed_2.jpg"); base = feat(src)
h, w = src.shape[:2]
def bright(im, g=0.7, c=1.15, wb=(0.92, 1.0, 1.08)):
    x = (im.astype(np.float32) / 255) ** g * c * np.array(wb, np.float32); return (np.clip(x, 0, 1) * 255).astype(np.uint8)
def shift(im, dx, dy, crop=0.0):
    M = np.float32([[1, 0, dx], [0, 1, dy]]); out = cv2.warpAffine(im, M, (im.shape[1], im.shape[0]), borderMode=cv2.BORDER_REFLECT)
    if crop: c = int(im.shape[1] * crop); out = cv2.resize(out[c:-c, c:-c], (im.shape[1], im.shape[0]))
    return out
rng = np.random.default_rng(0)
V = {
 "identical copy": src.copy(),
 "resized 45% + jpeg q60": cv2.imdecode(cv2.imencode(".jpg", cv2.resize(src, None, fx=.45, fy=.45, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 60])[1], 1),
 "darker/contrast/colour cast": bright(src, 1.5, 0.8, (1.1, 1.0, 0.9)),
 "much brighter": bright(src, 0.5, 1.1),
 "noisy + dim": np.clip(src.astype(np.float32) * 0.5 + rng.normal(0, 8, src.shape), 0, 255).astype(np.uint8),
 "handheld shift 0.6%": shift(src, w * .006, h * .004),
 "handheld shift 1.5%": shift(src, w * .015, h * .01),
 "shift 3%": shift(src, w * .03, h * .02),
 "shift 6%": shift(src, w * .06, h * .04),
 "crop-zoom 5%": shift(src, 0, 0, 0.05),
}
print("--- variants of one photo (bed_2) vs original")
for k, v in V.items(): show(k, F.compare(base, feat(v)))
for grp in ("Hotel Room A/Bedroom/*.jpg", "Hotel Room B/*.jpg"):
    files = sorted(glob.glob(f"tests/samples/{grp}")); fs = [feat(prev(f)) for f in files]
    print(f"--- different angles of the same room: {grp}")
    for (i, a), (j, b) in itertools.combinations(enumerate(fs), 2): show(f"{os.path.basename(files[i])[:-4]} vs {os.path.basename(files[j])[:-4]}", F.compare(a, b))
print("--- different rooms"); 
a = feat(prev("tests/samples/Hotel Room A/Bedroom/bed_2.jpg")); b = feat(prev("tests/samples/Hotel Room B/room_2.jpg")); c = feat(prev("tests/samples/Apartments/Modern/modern_living.jpg"))
show("hotel A vs hotel B", F.compare(a, b)); show("hotel A vs living", F.compare(a, c))
