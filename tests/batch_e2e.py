"""Real-photo batch check against a running instance (local or deployed).

    ROOMLIT_PASSWORD=... python tests/batch_e2e.py http://127.0.0.1:8765

Uploads 17 real photos (the same bed from several angles, a byte-identical copy, a darker copy, a nudged copy, a
same-named photo in another folder...) in random order over 3 parallel connections, twice:
  1. plain (Smart organise off, numbering off, no suffix): 17 in = 17 out, exact names, original order;
  2. the page's defaults: duplicates removed, photos arranged + numbered, folder called "<name> بعد التعديل".
Each ZIP and the single downloads are checked against what was uploaded.
"""
import concurrent.futures as cf, glob, hashlib, io, os, random, re, sys, time, urllib.parse, zipfile
import cv2, httpx, numpy as np
from PIL import Image

BASE = sys.argv[1].rstrip("/")
H = {"X-Requested-With": "roomlit"}
S = os.path.join(os.path.dirname(__file__), "samples")
c = httpx.Client(base_url=BASE, timeout=httpx.Timeout(600, connect=30), headers=H)
r = c.post("/api/login", json={"username": os.environ.get("ROOMLIT_USER", "admin"), "password": os.environ["ROOMLIT_PASSWORD"]})
assert r.status_code == 200, r.text


def read(p): return open(p, "rb").read()


def reencode(p, fn):
    im = cv2.imdecode(np.frombuffer(read(p), np.uint8), cv2.IMREAD_COLOR)
    return cv2.imencode(".jpg", fn(im), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def darker(im): return np.clip(255.0 * (im / 255.0) ** 1.7 * 0.7, 0, 255).astype(np.uint8)


def nudged(im): return np.roll(np.roll(im, 8, axis=1), 5, axis=0)


bed = sorted(glob.glob(f"{S}/Hotel Room A/Bedroom/*.jpg"))
room = sorted(glob.glob(f"{S}/Hotel Room B/*.jpg"))
kit = sorted(glob.glob(f"{S}/Classes/kitchen/*.jpg"))[:2]
B = "Villa Nord/Unit 1/"
files = {B + os.path.basename(p): read(p) for p in bed + room}                            # 6 + 5 similar-looking real photos
files[B + "bed_1 copy.jpg"] = read(bed[0])                                              # byte-identical, other name
files[B + "bed_1 darker.jpg"] = reencode(bed[0], darker)                                # same shot, much darker
files[B + "bed_2 nudged.jpg"] = reencode(bed[1], nudged)                                # same shot, camera moved a hair
files[B + "IMG_9.jpg"], files[B + "IMG_10.jpg"] = read(kit[0]), read(kit[1])
files[B + "Balcony/bed_1.jpg"] = read(bed[0])                                           # same name + same picture, other folder
assert len(files) == 17

SUFFIX = "بعد التعديل"
nat = lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
base_key = lambda n: (nat(os.path.splitext(n.rsplit("/", 1)[1])[0]), nat(os.path.splitext(n)[1]))      # name first, then extension


def fp(data):
    v = cv2.resize(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE), (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    v -= v.mean(); return v / (np.linalg.norm(v) + 1e-6)


ins = {n: fp(files[n]) for n in files}
twins = {n: {m for m in files if files[m] == files[n]} for n in files}


def fname(r):
    cd = r.headers["content-disposition"]
    return urllib.parse.unquote(cd.split("filename*=utf-8''")[1]) if "filename*=" in cd else cd.split('filename="')[1].rstrip('"')


MINE = []
BASE_FILES = c.get("/api/diag").json()["files_on_disk"]


def new_job(mode="premium"):
    jid = c.post("/api/jobs", json={"mode": mode}).json()["id"]
    MINE.append(jid)
    return jid


def run(label, start_body, zip_query):
    jid = new_job()
    order = list(files); random.Random(11).shuffle(order)

    def send(path):
        for _ in range(3):
            rr = c.post(f"/api/jobs/{jid}/files", params={"path": path}, content=files[path], headers={"Content-Type": "application/octet-stream"})
            if rr.status_code == 200: return rr.json()
        raise SystemExit(f"upload failed {path} {rr.status_code} {rr.text}")

    t0 = time.time()
    with cf.ThreadPoolExecutor(3) as ex:
        res = list(ex.map(send, order))
    assert sum(x["accepted"] for x in res) == 17
    assert send(order[0])["duplicate"] == 1                                               # a retried upload adds nothing

    def wait(pred, t=900):
        end = time.time() + t
        while time.time() < end:
            j = c.get(f"/api/jobs/{jid}").json()
            if pred(j): return j
            time.sleep(1.0)
        raise SystemExit("timeout " + str(j["counts"]))
    wait(lambda j: j["counts"]["ready"] + j["counts"]["failed"] == 17)
    assert c.post(f"/api/jobs/{jid}/start", json=start_body).status_code == 200
    j = wait(lambda j: j["phase"] in ("done", "failed") and j["counts"]["queued"] + j["counts"]["processing"] == 0)
    cnt = j["counts"]
    print(f"[{label}] input {cnt['total']}  edited {cnt['done']}  failed {cnt['failed']}  excluded {cnt['excluded']}  final {cnt['final']}  ({time.time() - t0:.0f}s)")
    assert cnt["failed"] == 0 and cnt["done"] == cnt["final"]
    r = c.get(f"/api/jobs/{jid}/download.zip{zip_query}")
    assert r.status_code == 200
    return jid, j, r, zipfile.ZipFile(io.BytesIO(r.content))


def check_pixels(z, entries):
    """entries: {zip name: original path}.  Same size, real format, and the closest original is its own."""
    for arc, orig in entries.items():
        a, b = Image.open(io.BytesIO(files[orig])), Image.open(io.BytesIO(z.read(arc)))
        assert a.size == b.size and b.format == "JPEG", arc
        o = fp(z.read(arc)); assert max(ins, key=lambda m: float(o @ ins[m])) in twins[orig], f"{arc} does not match its own original"


# ---------------------------------------------------------------- 1. plain: one in, one out
jid, j, r, z = run("plain", {"mode": "premium", "smart": False}, "?numbering=0&suffix=")
cnt = j["counts"]
assert (cnt["total"], cnt["done"], cnt["excluded"], cnt["renamed"]) == (17, 17, 0, 0) and all(not i["ex"] for i in j["items"])
names = z.namelist()
assert len(names) == 17 and len(set(names)) == 17 and set(names) == set(files), "ZIP must hold exactly the uploaded names"
expected = []
for folder in sorted({n.rsplit("/", 1)[0] for n in files}, key=nat):
    expected += sorted((n for n in files if n.rsplit("/", 1)[0] == folder), key=base_key)
assert names == expected, "ZIP order must be the original file-name order"
check_pixels(z, {n: n for n in names})
for it in j["items"]:
    d = c.get(f"/api/jobs/{jid}/items/{it['id']}/download")
    assert fname(d) == it["name"] and hashlib.sha256(d.content).digest() == hashlib.sha256(z.read(it["out"])).digest(), it["name"]
print("OK plain: 17 in = 17 out, exact names/folders/extensions, original order, each output matches its own input, single downloads identical")
print("   order:", [n.split("Unit 1/")[1] for n in names])

# ---------------------------------------------------------------- 2. the page's defaults: smart + numbered + suffix
jid, j, r, z = run("default", {"mode": "premium"}, f"?numbering=1&suffix={urllib.parse.quote(SUFFIX)}")
cnt = j["counts"]
gone = sorted(i["name"] for i in j["items"] if i["ex"] and i["dir"].endswith("Unit 1"))
print("   removed as duplicates:", gone)
assert {"bed_1 copy.jpg", "bed_1 darker.jpg"} <= set(gone) and "bed_1.jpg" not in gone and cnt["excluded"] >= 2 and cnt["final"] == 17 - cnt["excluded"]
assert next(i for i in j["items"] if i["dir"].endswith("Balcony"))["ex"] is False, "another apartment is never merged"
names = z.namelist()
assert fname(r) == f"Villa Nord {SUFFIX}.zip", fname(r)
assert len(names) == cnt["final"] and all(n.startswith(f"Villa Nord {SUFFIX}/") for n in names)
by_folder = {}
for n in names:
    folder, base = n.rsplit("/", 1); by_folder.setdefault(folder, []).append(base)
for folder, bases in by_folder.items():
    assert [b[:5] for b in bases] == [f"{k:02d} - " for k in range(1, len(bases) + 1)], folder       # numbered 01, 02, ... in the ZIP order
entries = {n: n.replace(f"Villa Nord {SUFFIX}/", "Villa Nord/", 1).rsplit("/", 1)[0] + "/" + n.rsplit(" - ", 1)[1] for n in names}
assert all(o in files for o in entries.values()), "every delivered file is one of the uploaded names (after its number)"
check_pixels(z, entries)
print(f"OK default: {cnt['total']} in, {cnt['excluded']} duplicates set aside, {len(names)} delivered, numbered, folder '{SUFFIX}' added; zip: {fname(r)}")
print("   first entries:", names[:3])

# ---------------------------------------------------------------- 3. Pro Listing + Enhance resolution + Retouch
def small_copy(p, long_edge=1200):
    im = cv2.imdecode(np.frombuffer(read(p), np.uint8), cv2.IMREAD_COLOR); k = long_edge / max(im.shape[:2])
    return cv2.imencode(".jpg", cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def pole(p):
    im = cv2.imdecode(np.frombuffer(read(p), np.uint8), cv2.IMREAD_COLOR); h, w = im.shape[:2]
    cv2.line(im, (int(w * .22), int(h * .12)), (int(w * .27), int(h * .62)), (43, 90, 138), max(8, w // 150), cv2.LINE_AA)
    return cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


jid = new_job("pro")
small, big = small_copy(room[0]), pole(room[1])
for name, data in (("Pro Villa/Unit 2/small_1200.jpg", small), ("Pro Villa/Unit 2/with_pole.jpg", big)):
    assert c.post(f"/api/jobs/{jid}/files", params={"path": name}, content=data, headers={"Content-Type": "application/octet-stream"}).status_code == 200
j = c.get(f"/api/jobs/{jid}").json()
end = time.time() + 300
while j["counts"]["ready"] < 2 and time.time() < end: time.sleep(1); j = c.get(f"/api/jobs/{jid}").json()
assert c.post(f"/api/jobs/{jid}/start", json={"mode": "pro", "smart": False, "enlarge": True}).status_code == 200
while not (j["counts"]["done"] == 2) and time.time() < end: time.sleep(1); j = c.get(f"/api/jobs/{jid}").json()
by = {i["name"]: i for i in j["items"]}
assert j["counts"]["done"] == 2 and all(i["mode"] == "pro" for i in j["items"])
assert (by["small_1200.jpg"]["w"], by["small_1200.jpg"]["h"]) == (2048, round(2048 * Image.open(io.BytesIO(small)).size[1] / 1200)), by["small_1200.jpg"]
assert by["with_pole.jpg"]["w"] == Image.open(io.BytesIO(big)).size[0]                  # big photos keep their size
print(f"OK pro + enhance resolution: 1200px photo -> {by['small_1200.jpg']['w']}x{by['small_1200.jpg']['h']}, {by['with_pole.jpg']['w']}px photo untouched in size, mode {by['with_pole.jpg']['mode']}")
it = by["with_pole.jpg"]
first = np.asarray(Image.open(io.BytesIO(c.get(f"/api/jobs/{jid}/items/{it['id']}/download").content)).convert("RGB")).astype(int)
W0, H0 = Image.open(io.BytesIO(big)).size
ops = [{"t": "remove", "r": 0.0075, "pts": [[0.22, 0.12], [0.27, 0.62]]}]
assert c.post(f"/api/jobs/{jid}/items/{it['id']}/retouch", json={"ops": ops}).json() == {"ok": True, "queued": True}
end = time.time() + 300
while time.time() < end:
    j = c.get(f"/api/jobs/{jid}").json(); cur = next(i for i in j["items"] if i["id"] == it["id"])
    if cur["v"] == it["v"] + 1 and j["counts"]["done"] == 2: break
    time.sleep(1)
second = np.asarray(Image.open(io.BytesIO(c.get(f"/api/jobs/{jid}/items/{it['id']}/download").content)).convert("RGB")).astype(int)
x0, x1 = int(W0 * .22) - 20, int(W0 * .27) + 20; y0, y1 = int(H0 * .12), int(H0 * .62)
changed = np.abs(first - second)[y0:y1, x0:x1].mean(); far = np.abs(first - second)[:, int(W0 * .6):].mean()
print(f"OK retouch: pole area changed by {changed:.1f} levels, area far away by {far:.2f} (the rest of the photo is untouched), name still {cur['out']}")
assert changed > 3 and far < 0.5 and cur["rt"] == 1 and cur["out"] == "Pro Villa/Unit 2/with_pole.jpg"

for jid in MINE:
    c.delete(f"/api/jobs/{jid}")
d = c.get("/api/diag").json(); assert d["files_on_disk"] <= BASE_FILES, d
print("cleanup OK: this script's files are gone;  peak memory: web", d["web_peak_rss_mb"], "MB, image worker", d["worker_peak_mb"], "MB, organizer", d["organizer_peak_mb"], "MB")
