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


def run(label, start_body, zip_query):
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
c.delete(f"/api/jobs/{jid}")
d = c.get("/api/diag").json(); assert d["files_on_disk"] == 0, d; print("cleanup OK: 0 files left on the server")
