"""A realistic batch (18 photos, similar-looking ones, tricky names) must come back 1:1, in order, under its own names.

Plain mode (Smart organise unticked, numbering off, no suffix): nothing is removed, nothing is moved, nothing is renamed.  Every check below compares the ZIP /
single downloads against what was uploaded, never against what the app thinks it did.
"""
import hashlib, io, random, urllib.parse, zipfile
import cv2
import numpy as np
from PIL import Image
from . import synth
from .test_api import H, up, wait, client, authed  # noqa: F401

W, HT = 640, 480


def marked(img, n):
    """Stamp a big unique marker so every file can be told apart even when the rooms look the same."""
    out = img.copy()
    cv2.putText(out, str(n), (40, 330), cv2.FONT_HERSHEY_SIMPLEX, 9, (0, 0, 0), 34)
    cv2.putText(out, str(n), (40, 330), cv2.FONT_HERSHEY_SIMPLEX, 9, (255, 255, 255), 16)
    return out


def jpg(img, q=92) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()


def png(img) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


def webp(img) -> bytes:
    buf = io.BytesIO(); Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(buf, "WEBP", quality=92); return buf.getvalue()


def build():
    A, B, C = synth.layout(501, W, HT), synth.layout(502, W, HT), synth.layout(503, W, HT)
    a1 = jpg(marked(A, 11))
    base = "Villa Nord/Unit 1/"
    files = {
        # one room shot four ways: the original, a byte-identical copy under another name, much darker, nudged sideways
        base + "IMG_001.jpg": a1,
        base + "IMG_001 copy.jpg": a1,
        base + "IMG_002.jpg": jpg(marked(synth.relit(A, 1.7, 0.7, (1.1, 1.0, 0.9)), 12)),
        base + "IMG_003.jpg": jpg(marked(synth.shifted(A, 6, 4), 13)),
        # a second room from two angles, a third room twice with different light
        base + "IMG_004.jpg": jpg(marked(B, 14)),
        base + "IMG_005.jpg": jpg(marked(synth.other_angle(B), 15)),
        base + "IMG_9.jpg": jpg(marked(C, 16)),
        base + "IMG_10.jpg": jpg(marked(synth.relit(C, 1.3, 0.9, (1.0, 1.0, 1.0)), 17)),
        base + "IMG_100.jpg": jpg(marked(synth.layout(504, 800, 600), 18)),
        # names and formats that must come back exactly as they went in
        base + "IMG_007.JPG": jpg(marked(synth.layout(505, W, HT), 19)),
        base + "room.jpeg": jpg(marked(synth.layout(506, W, HT), 20)),
        base + "IMG_008.png": png(marked(synth.layout(507, W, HT), 21)),
        base + "fake_png.png": jpg(marked(synth.layout(508, W, HT), 22)),          # JPEG bytes called .png
        base + "real_png.jpg": png(marked(synth.layout(509, W, HT), 23)),          # PNG bytes called .jpg
        base + "view.webp": webp(marked(synth.layout(510, W, HT), 24)),
        base + "غرفة النوم ١.jpg": jpg(marked(synth.layout(511, W, HT), 25)),
        base + "bed (1).jpg": jpg(marked(synth.layout(512, W, HT), 26)),
        # same file name AND the same picture, but another folder: never merged
        base + "Balcony/IMG_001.jpg": a1,
    }
    expected = [base + n for n in (
        "bed (1).jpg", "fake_png.png", "IMG_001.jpg", "IMG_001 copy.jpg", "IMG_002.jpg", "IMG_003.jpg", "IMG_004.jpg",
        "IMG_005.jpg", "IMG_007.JPG", "IMG_008.png", "IMG_9.jpg", "IMG_10.jpg", "IMG_100.jpg", "real_png.jpg", "room.jpeg",
        "view.webp", "غرفة النوم ١.jpg")] + [base + "Balcony/IMG_001.jpg"]
    return files, expected


FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


def fingerprint(data: bytes):
    """Small, exposure-insensitive signature of a picture (zero mean, unit variance)."""
    im = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    v = cv2.resize(im, (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    v -= v.mean()
    return v / (np.linalg.norm(v) + 1e-6)


def test_batch_of_18_comes_back_one_to_one_in_order_under_exact_names(authed):
    c = authed
    files, expected = build()
    jid = c.post("/api/jobs", json={"mode": "premium"}, headers=H).json()["id"]
    paths = list(files)
    random.Random(5).shuffle(paths)                                                  # photos arrive in any order
    for p in paths:
        r = up(c, jid, p, files[p])
        assert r.status_code == 200 and r.json()["accepted"] == 1, p
    # a retried request / the same folder added twice must not create a second photo
    r = up(c, jid, "Villa Nord/Unit 1/IMG_001.jpg", files["Villa Nord/Unit 1/IMG_001.jpg"])
    assert r.status_code == 200 and r.json() == {"accepted": 0, "ignored": 0, "duplicate": 1}
    wait(c, jid, lambda j: j["counts"]["ready"] + j["counts"]["failed"] == len(files))
    assert c.post(f"/api/jobs/{jid}/start", json={"mode": "premium", "smart": False}, headers=H).status_code == 200
    j = wait(c, jid, lambda j: j["phase"] in ("done", "failed") and j["counts"]["queued"] + j["counts"]["processing"] == 0)

    # ---- input count = output count, nothing skipped, nothing removed, nothing renamed
    cnt = j["counts"]
    assert (cnt["total"], cnt["done"], cnt["failed"], cnt["excluded"], cnt["final"], cnt["renamed"]) == (18, 18, 0, 0, 18, 0)
    assert j["already"] == 1 and len(j["items"]) == 18
    assert all(not i["ex"] and not i["renamed"] and i["dup_of"] is None for i in j["items"])

    r = c.get(f"/api/jobs/{jid}/download.zip?numbering=0&suffix=")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert len(names) == len(files) == 18 and len(set(names)) == 18                  # no extra file, no duplicate entry
    assert set(names) == set(files)                                                  # exact names, folders and extensions
    assert names == expected                                                         # original (file-name) order, folder by folder
    assert [i["out"] for i in sorted(j["items"], key=lambda i: (i["dir"] != "Villa Nord/Unit 1", i["pos"]))] == expected

    # ---- every output is the edited version of ITS OWN input (and keeps size and real format)
    ins = {n: fingerprint(files[n]) for n in files}
    same_bytes = {n: {m for m in files if files[m] == files[n]} for n in files}
    for n in names:
        data = z.read(n)
        src = Image.open(io.BytesIO(files[n]))
        out = Image.open(io.BytesIO(data))
        assert out.size == src.size, n                                               # no crop, no resize
        want = FORMAT[n[n.rindex("."):].lower()]
        assert out.format == want, (n, out.format)                                   # the container matches the name
        fp = fingerprint(data)
        best = max(ins, key=lambda m: float(fp @ ins[m]))
        assert best in same_bytes[n], (n, best)                                      # closest original is itself (or its byte-identical twin)
    assert z.read("Villa Nord/Unit 1/IMG_001.jpg") == z.read("Villa Nord/Unit 1/IMG_001 copy.jpg")      # identical input -> identical output

    # ---- single downloads: same name, same bytes as in the ZIP
    for it in j["items"]:
        d = c.get(f"/api/jobs/{jid}/items/{it['id']}/download")
        assert d.status_code == 200
        cd = d.headers["content-disposition"]
        fname = urllib.parse.unquote(cd.split("filename*=utf-8''")[1]) if "filename*=" in cd else cd.split('filename="')[1].rstrip('"')
        assert fname == it["name"], (fname, it["name"])
        assert hashlib.sha256(d.content).digest() == hashlib.sha256(z.read(it["out"])).digest()

    # ---- the gallery numbers are the file order too, and the photos-only ZIP has no log inside
    parent = sorted((i for i in j["items"] if i["dir"] == "Villa Nord/Unit 1"), key=lambda i: i["pos"])
    assert [i["pos"] for i in parent] == list(range(1, 18))
    assert not any(n.endswith(".csv") for n in names)
    assert c.get(f"/api/jobs/{jid}/log.csv").status_code == 200
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_a_zip_is_never_built_while_photos_are_still_being_edited(authed):
    import app.main as main
    c = authed
    files = {"R/1/a.jpg": jpg(synth.layout(520, W, HT)), "R/1/b.jpg": jpg(synth.layout(521, W, HT))}
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    for p, d in files.items():
        up(c, jid, p, d)
    wait(c, jid, lambda j: j["counts"]["ready"] == 2)
    c.post(f"/api/jobs/{jid}/start", json={"smart": False}, headers=H)
    wait(c, jid, lambda j: j["counts"]["done"] == 2)
    job = main.store.jobs[jid]
    victim = next(iter(job.items.values()))
    victim.status = "processing"                                                      # as if the editor were still busy with it
    r = c.get(f"/api/jobs/{jid}/download.zip?numbering=0&suffix=")
    assert r.status_code == 409 and r.json()["error"] == "still_working"
    victim.status = "done"
    assert len(zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip?numbering=0&suffix=").content)).namelist()) == 2
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_two_different_photos_with_the_same_path_are_both_kept_and_flagged(authed):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    assert up(c, jid, "R/1/a.jpg", jpg(synth.layout(530, W, HT))).json()["accepted"] == 1
    assert up(c, jid, "R/1/a.jpg", jpg(synth.layout(531, W, HT))).json()["accepted"] == 1      # different picture, same path
    j = wait(c, jid, lambda j: j["counts"]["ready"] == 2)
    assert j["already"] == 0 and j["counts"]["renamed"] == 1 and sorted(i["out"] for i in j["items"]) == ["R/1/a (2).jpg", "R/1/a.jpg"]
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_adding_photos_later_keeps_one_output_per_original_in_name_order(authed):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    for n in (3, 1):
        up(c, jid, f"R/1/{n}.jpg", jpg(synth.layout(540 + n, W, HT)))
    wait(c, jid, lambda j: j["counts"]["ready"] == 2)
    c.post(f"/api/jobs/{jid}/start", json={"smart": False}, headers=H)
    wait(c, jid, lambda j: j["counts"]["done"] == 2)
    for n in (10, 2):
        up(c, jid, f"R/1/{n}.jpg", jpg(synth.layout(540 + n, W, HT)))
    up(c, jid, "R/1/1.jpg", jpg(synth.layout(541, W, HT)))                           # the same file again: ignored
    wait(c, jid, lambda j: j["counts"]["ready"] == 2)
    c.post(f"/api/jobs/{jid}/start", json={"smart": False}, headers=H)
    j = wait(c, jid, lambda j: j["counts"]["done"] == 4)
    assert j["counts"]["total"] == 4 and j["already"] == 1
    assert zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip?numbering=0&suffix=").content)).namelist() == \
        ["R/1/1.jpg", "R/1/2.jpg", "R/1/3.jpg", "R/1/10.jpg"]
    c.delete(f"/api/jobs/{jid}", headers=H)
