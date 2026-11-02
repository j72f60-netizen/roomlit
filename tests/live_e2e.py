"""End-to-end test against a deployed instance.  Usage: python tests/live_e2e.py https://host PASSWORD_FILE"""
import glob, io, json, os, sys, time, zipfile
import httpx
from PIL import Image

BASE = sys.argv[1].rstrip("/")
pw = [l.split("=", 1)[1].strip() for l in open(sys.argv[2]) if l.startswith("APP_PASSWORD=")][0]
H = {"X-Requested-With": "roomlit"}
S = os.path.join(os.path.dirname(__file__), "samples")
c = httpx.Client(base_url=BASE, timeout=httpx.Timeout(300, connect=30), headers=H)
R = {}

def step(name): print(f"\n=== {name}", flush=True)
def wait(jid, pred, t=900, every=1.5):
    end = time.time() + t
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").json()
        if pred(j): return j
        time.sleep(every)
    raise SystemExit(f"timeout waiting: {json.dumps(j['counts'])}")
def upload(jid, rel, path=None, data=None):
    hdr = {"Content-Type": "application/octet-stream"}
    if data is not None:
        r = c.post(f"/api/jobs/{jid}/files", params={"path": rel}, content=data, headers=hdr)
    else:
        with open(path, "rb") as f:
            r = c.post(f"/api/jobs/{jid}/files", params={"path": rel}, content=f, headers=hdr)
    assert r.status_code == 200, (rel, r.status_code, r.text)
    return r.json()
def diag(): return c.get("/api/diag").json()

r = c.post("/api/login", json={"username": "admin", "password": pw}); assert r.status_code == 200, r.text
for old in c.get("/api/jobs").json()["jobs"]: c.delete(f"/api/jobs/{old['id']}")
print("diag at start:", diag())

# ---------------------------------------------------------------- 1. nested folder, 12 photos, premium
step("1. folder upload (12 photos, nested), Premium")
layout = {"1": sorted(glob.glob(f"{S}/Hotel Room A/Bedroom/*.jpg")), "02": sorted(glob.glob(f"{S}/Hotel Room B/*.jpg")), "3": sorted(glob.glob(f"{S}/Apartments/Tianhe/*.jpg"))}
orig_dims, total_bytes, names = {}, 0, []
jid = c.post("/api/jobs", json={"mode": "premium"}).json()["id"]
t0 = time.time()
for folder, files in layout.items():
    for f in files:
        rel = f"Photos Al Khuzama/{folder}/{os.path.basename(f)}"
        upload(jid, rel, path=f); names.append(rel); total_bytes += os.path.getsize(f)
        orig_dims[rel] = Image.open(f).size
upload(jid, "Photos Al Khuzama/1/notes.txt", data=b"ignore me")
t_up = time.time() - t0
j = wait(jid, lambda j: j["counts"]["ready"] == len(names)); t_ready = time.time() - t0
print(f"uploaded {len(names)} photos / {total_bytes/1e6:.1f} MB in {t_up:.1f}s; all analysed {t_ready - t_up:.1f}s later; ignored={j['ignored']}")
assert c.post(f"/api/jobs/{jid}/start", json={"mode": "premium"}).json()["queued"] == len(names)
t1 = time.time(); j = wait(jid, lambda j: j["counts"]["done"] + j["counts"]["failed"] == len(names)); t_proc = time.time() - t1
assert j["counts"]["done"] == len(names), j["counts"]
per = [i["sec"] for i in j["items"]]
print(f"PROCESSED {len(names)} photos in {t_proc:.1f}s wall-clock (server per-photo avg {sum(per)/len(per):.1f}s, max {max(per):.1f}s)")
R["batch12"] = {"photos": len(names), "megabytes_in": round(total_bytes/1e6, 1), "upload_s": round(t_up, 1), "analyse_s": round(t_ready - t_up, 1), "process_wall_s": round(t_proc, 1), "avg_per_photo_s": round(sum(per)/len(per), 1)}
d = diag(); print("diag after batch:", d); R["mem_after_batch"] = d

step("2. ZIP download: structure, filenames, dimensions, EXIF")
z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip").content))
expected = {}
for rel in names:
    p = rel.split("/"); expected[f"{p[0]} - Edited/{p[1]}/Edited - Airbnb/{p[2]}"] = rel
assert sorted(z.namelist()) == sorted(expected), (sorted(z.namelist())[:3], sorted(expected)[:3])
for arc, rel in expected.items():
    im = Image.open(io.BytesIO(z.read(arc)))
    assert im.size == orig_dims[rel], (arc, im.size, orig_dims[rel])
print(f"OK: {len(expected)} files, folder structure and filenames identical to the plan, every image has the same pixel dimensions as its original")
print("sample entries:", sorted(z.namelist())[:3])
print("downloaded flag after ZIP:", {k: v for k, v in c.get(f"/api/jobs/{jid}").json().items() if k in ("downloaded", "expires_in")})

step("3. all three modes on the same job (reprocess all)")
means = {}
def mean_luma(zf):
    import numpy as np
    vals = []
    for n in zf.namelist():
        im = Image.open(io.BytesIO(zf.read(n))).convert("L"); im.thumbnail((400, 400)); vals.append(float(np.asarray(im).mean()))
    return sum(vals) / len(vals)
for mode in ("natural", "premium", "bright"):
    t = time.time()
    assert c.post(f"/api/jobs/{jid}/reprocess", json={"mode": mode}).status_code == 200
    time.sleep(1.0)
    j = wait(jid, lambda j: j["counts"]["done"] == len(names) and all(i["mode"] == mode for i in j["items"]))
    zz = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip").content))
    means[mode] = mean_luma(zz); print(f"{mode:8s} reprocessed {len(names)} photos in {time.time()-t:.1f}s, mean brightness {means[mode]:.1f}/255")
assert means["natural"] < means["premium"] < means["bright"]
R["mode_brightness"] = {k: round(v, 1) for k, v in means.items()}

step("4. reprocess ONE photo + download ONE photo + previews")
item = j["items"][0]; v0 = item["v"]
assert c.post(f"/api/jobs/{jid}/items/{item['id']}/reprocess", json={"mode": "premium"}).status_code == 200
time.sleep(0.8); j = wait(jid, lambda j: next(i for i in j["items"] if i["id"] == item["id"])["v"] == v0 + 1 and j["counts"]["done"] == len(names))
one = c.get(f"/api/jobs/{jid}/items/{item['id']}/download"); assert one.status_code == 200 and Image.open(io.BytesIO(one.content)).size == (item["w"], item["h"])
for k in ("before", "after", "thumb"):
    p = c.get(f"/api/jobs/{jid}/items/{item['id']}/preview/{k}"); assert p.status_code == 200 and p.headers["content-type"] == "image/jpeg"
print("OK single reprocess, single download, before/after/thumb previews")
assert c.delete(f"/api/jobs/{jid}").status_code == 200
d = diag(); print("diag after delete:", d); assert d["files_on_disk"] == 0 and d["jobs"] == 0; R["after_delete"] = d

# ---------------------------------------------------------------- 5. ZIP upload
step("5. ZIP upload (with junk + traversal entries)")
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
    for f in sorted(glob.glob(f"{S}/Hotel Room B/*.jpg"))[:4]:
        zf.write(f, f"Villa Nord/Bedroom/{os.path.basename(f)}")
    zf.writestr("__MACOSX/Villa Nord/._x.jpg", b"junk"); zf.writestr("Villa Nord/.DS_Store", b"junk"); zf.writestr("../../evil.jpg", b"x"); zf.writestr("Villa Nord/readme.txt", b"hi")
jid = c.post("/api/jobs", json={}).json()["id"]
t = time.time(); r = upload(jid, "Villa Nord.zip", data=buf.getvalue()); print("zip upload:", r, f"({len(buf.getvalue())/1e6:.1f} MB, {time.time()-t:.1f}s)")
j = wait(jid, lambda j: j["counts"]["ready"] == 4); print("ignored:", j["ignored"])
c.post(f"/api/jobs/{jid}/start", json={"mode": "bright"}); j = wait(jid, lambda j: j["counts"]["done"] == 4)
zz = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip").content)); print("ZIP result:", sorted(zz.namelist()))
assert all(n.startswith("Villa Nord - Edited/Bedroom/Edited - Airbnb/") for n in zz.namelist()) and len(zz.namelist()) == 4
c.delete(f"/api/jobs/{jid}")

# ---------------------------------------------------------------- 6. big photo + failures
step("6. 37-megapixel photo, corrupt file, over-limit photo")
big = f"{S}/Apartments/Rio/living_big.jpg"; w, h = Image.open(big).size
jid = c.post("/api/jobs", json={"mode": "premium"}).json()["id"]
upload(jid, "Big/living_big.jpg", path=big); upload(jid, "Big/corrupt.jpg", data=b"this is not a jpeg" * 100)
huge = io.BytesIO(); Image.new("L", (9000, 5000)).save(huge, "PNG"); upload(jid, "Big/too_many_pixels.png", data=huge.getvalue())
j = wait(jid, lambda j: j["counts"]["ready"] + j["counts"]["failed"] == 3)
for i in j["items"]: print(f"  {i['name']:22s} {i['status']:7s} {i['err'] or ''}")
t = time.time(); c.post(f"/api/jobs/{jid}/start", json={"mode": "premium"}); j = wait(jid, lambda j: j["counts"]["done"] == 1)
big_item = next(i for i in j["items"] if i["name"] == "living_big.jpg"); print(f"{w}x{h} ({w*h/1e6:.1f} MP) processed in {big_item['sec']}s server-side; output {big_item['w']}x{big_item['h']} (dimensions preserved: {(big_item['w'], big_item['h']) == (w, h)})")
d = diag(); print("diag after big photo:", d); R["big_photo"] = {"megapixels": round(w*h/1e6, 1), "seconds": big_item["sec"], "diag": d}
c.delete(f"/api/jobs/{jid}")
step("7. fully failed job removes its files by itself")
jid = c.post("/api/jobs", json={}).json()["id"]; upload(jid, "X/bad.jpg", data=b"zzz" * 200)
j = wait(jid, lambda j: j["counts"]["failed"] == 1 and j["purged"]); d = diag(); print("failed job purged:", j["purged"], "| files on disk:", d["files_on_disk"]); assert d["files_on_disk"] == 0
c.delete(f"/api/jobs/{jid}")
print("\nSUMMARY", json.dumps(R, indent=1))
