"""Real-photo batch check against a running instance (local or deployed).

    ROOMLIT_PASSWORD=... python tests/batch_e2e.py http://127.0.0.1:8765

Uploads 17 real photos (the same bed from several angles, a byte-identical copy, a darker copy, a nudged copy, a
same-named photo in another folder...) in random order over 3 parallel connections, edits them with the default
settings and checks the ZIP and the single downloads against what was uploaded.
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

for old in c.get("/api/jobs").json()["jobs"]:
    c.delete(f"/api/jobs/{old['id']}")
jid = c.post("/api/jobs", json={"mode": "premium"}).json()["id"]
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
assert send(order[0])["duplicate"] == 1                                                   # a retried upload adds nothing
def wait(pred, t=900):
    end = time.time() + t
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").json()
        if pred(j): return j
        time.sleep(1.0)
    raise SystemExit("timeout " + str(j["counts"]))
wait(lambda j: j["counts"]["ready"] + j["counts"]["failed"] == 17)
assert c.post(f"/api/jobs/{jid}/start", json={"mode": "premium"}).status_code == 200      # default: no smart organisation
j = wait(lambda j: j["phase"] in ("done", "failed") and j["counts"]["queued"] + j["counts"]["processing"] == 0)
wall = time.time() - t0

cnt = j["counts"]
print(f"input {cnt['total']}  edited {cnt['done']}  failed {cnt['failed']}  excluded {cnt['excluded']}  renamed {cnt['renamed']}  ({wall:.0f}s)")
assert (cnt["total"], cnt["done"], cnt["failed"], cnt["excluded"], cnt["renamed"]) == (17, 17, 0, 0, 0)
assert all(not i["ex"] and i["dup_of"] is None for i in j["items"])

z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip").content))
names = z.namelist()
assert len(names) == 17 and len(set(names)) == 17 and set(names) == set(files), "ZIP must hold exactly the uploaded names"
nat = lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
base_key = lambda n: (nat(os.path.splitext(n.rsplit("/", 1)[1])[0]), nat(os.path.splitext(n)[1]))      # name first, then extension
expected = []
for folder in sorted({n.rsplit("/", 1)[0] for n in files}, key=nat):
    expected += sorted((n for n in files if n.rsplit("/", 1)[0] == folder), key=base_key)
assert names == expected, "ZIP order must be the original file-name order"


def fp(data):
    v = cv2.resize(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE), (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    v -= v.mean(); return v / (np.linalg.norm(v) + 1e-6)


ins = {n: fp(files[n]) for n in files}
twins = {n: {m for m in files if files[m] == files[n]} for n in files}
for n in names:
    a, b = Image.open(io.BytesIO(files[n])), Image.open(io.BytesIO(z.read(n)))
    assert a.size == b.size and b.format == "JPEG", n
    o = fp(z.read(n)); assert max(ins, key=lambda m: float(o @ ins[m])) in twins[n], f"{n} does not match its own original"
for it in j["items"]:
    d = c.get(f"/api/jobs/{jid}/items/{it['id']}/download")
    cd = d.headers["content-disposition"]
    name = urllib.parse.unquote(cd.split("filename*=utf-8''")[1]) if "filename*=" in cd else cd.split('filename="')[1].rstrip('"')
    assert name == it["name"] and hashlib.sha256(d.content).digest() == hashlib.sha256(z.read(it["out"])).digest(), it["name"]
print("OK: 17 in = 17 out, exact names/folders/extensions, original order, each output matches its own input, single downloads identical to the ZIP")
print("zip order:", [n.split("Unit 1/")[1] for n in names])
c.delete(f"/api/jobs/{jid}")
d = c.get("/api/diag").json(); assert d["files_on_disk"] == 0, d; print("cleanup OK: 0 files left on the server")
