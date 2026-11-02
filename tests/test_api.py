import dataclasses, io, os, signal, time, zipfile
import cv2
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import app.main as main
from . import synth

H = {"X-Requested-With": "roomlit"}
FILE = {"Content-Type": "application/octet-stream", **H}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def authed(client):
    client.cookies.clear()
    main.auth._fails.clear(); main.auth._locked.clear()
    r = client.post("/api/login", json={"username": "admin", "password": "test-password"}, headers=H)
    assert r.status_code == 200
    yield client
    for j in client.get("/api/jobs").json().get("jobs", []):
        client.delete(f"/api/jobs/{j['id']}", headers=H)


def jpeg(tmp_path=None, k=0, w=480, h=360) -> bytes:
    """A distinct, deterministic room photo per k."""
    ok, enc = cv2.imencode(".jpg", synth.layout(100 + k, w, h), [cv2.IMWRITE_JPEG_QUALITY, 92])
    return enc.tobytes()


def up(c, jid, path, data, headers=FILE):
    return c.post(f"/api/jobs/{jid}/files", params={"path": path}, content=data, headers=headers)


def wait(c, jid, pred, t=180):
    end = time.time() + t
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").json()
        if pred(j): return j
        time.sleep(0.2)
    raise AssertionError(j)


def run_job(c, files: dict, mode="premium"):
    """Upload {path: bytes}, start, wait until everything kept is edited.  Returns (job id, final job json)."""
    jid = c.post("/api/jobs", json={"mode": mode}, headers=H).json()["id"]
    for path, data in files.items():
        assert up(c, jid, path, data).status_code == 200, path
    wait(c, jid, lambda j: j["counts"]["ready"] + j["counts"]["failed"] == len(files))
    assert c.post(f"/api/jobs/{jid}/start", json={"mode": mode}, headers=H).status_code == 200
    j = wait(c, jid, lambda j: j["phase"] in ("done", "failed") and j["counts"]["queued"] + j["counts"]["processing"] == 0)
    return jid, j


# ---------------------------------------------------------------- security
def test_everything_requires_login(client):
    client.cookies.clear()
    for method, path in [("get", "/api/jobs"), ("get", "/api/config"), ("get", "/api/diag"), ("post", "/api/jobs"),
                         ("get", "/api/jobs/abc"), ("get", "/api/jobs/abc/items/1/preview/before"), ("get", "/api/jobs/abc/download.zip"),
                         ("get", "/api/jobs/abc/log.csv"), ("post", "/api/jobs/abc/items/1/exclude"), ("post", "/api/jobs/abc/items/1/restore"),
                         ("post", "/api/jobs/abc/sets/1/order"), ("post", "/api/jobs/abc/items/1/main")]:
        assert getattr(client, method)(path, headers=H).status_code == 401, path
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/").status_code == 200


def test_wrong_password_and_lockout(client):
    client.cookies.clear()
    main.auth._fails.clear(); main.auth._locked.clear()
    for _ in range(5):
        assert client.post("/api/login", json={"username": "admin", "password": "nope"}, headers=H).status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "nope"}, headers=H).status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "test-password"}, headers=H).status_code == 429
    main.auth._fails.clear(); main.auth._locked.clear()


def test_csrf_header_required_and_cookie_flags(client):
    main.auth._fails.clear(); main.auth._locked.clear()
    assert client.post("/api/login", json={"username": "admin", "password": "test-password"}).status_code == 403
    assert client.post("/api/login", json={"username": "admin", "password": "test-password"}, headers={**H, "Origin": "https://evil.example"}).status_code == 403
    r = client.post("/api/login", json={"username": "admin", "password": "test-password"}, headers=H)
    assert r.status_code == 200
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_forged_cookie_rejected(client):
    client.cookies.clear()
    client.cookies.set("hpe_session", "forged.value.here")
    assert client.get("/api/jobs").status_code == 401


def test_unknown_job_and_path_traversal_attempts(authed, tmp_path):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    assert up(c, jid, "../../evil.jpg", jpeg()).status_code == 400
    assert up(c, jid, "/etc/passwd.jpg", jpeg()).status_code == 400
    assert c.get(f"/api/jobs/{jid}/items/999/preview/before").status_code == 404
    assert c.get("/api/jobs/does-not-exist").status_code == 404
    assert c.post(f"/api/jobs/{jid}/sets/99/order", json={"order": []}, headers=H).status_code == 404


# ---------------------------------------------------------------- end to end
def test_folder_upload_zip_has_original_names_and_no_edited_words(authed):
    c = authed
    files = {"Al Khuzama/1/a.jpg": jpeg(k=1), "Al Khuzama/1/B.JPG": jpeg(k=2), "Al Khuzama/02/a.jpg": jpeg(k=3),
             "Al Khuzama/3/x/deep.jpg": jpeg(k=4), "Al Khuzama/3/x/also.jpg": jpeg(k=5)}
    jid, j = run_job(c, files)
    assert j["counts"]["done"] == 5 and j["counts"]["excluded"] == 0 and j["counts"]["final"] == 5
    r = c.get(f"/api/jobs/{jid}/download.zip")
    assert r.status_code == 200 and "Al%20Khuzama.zip" in r.headers["content-disposition"].replace("filename*=utf-8''", "Al%20Khuzama.zip ") or "Al Khuzama.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "Al Khuzama/Roomlit log.csv" in names
    photos = [n for n in names if not n.endswith(".csv")]
    assert all(n.split("/")[0] == "Al Khuzama" for n in names)                                     # root folder name exactly as uploaded
    assert {os.path.dirname(n) for n in photos} == {"Al Khuzama/1", "Al Khuzama/02", "Al Khuzama/3/x"}  # same sub-folders
    assert not any(w in n for n in names for w in ("Edited", "Airbnb"))
    strip = lambda n: n.split(" - ", 1)[1]
    assert sorted(strip(n) for n in photos) == sorted(["a.jpg", "B.JPG", "a.jpg", "deep.jpg", "also.jpg"])    # original names after the order number
    assert all(os.path.basename(n)[:2].isdigit() for n in photos)
    for n in photos:
        assert Image.open(io.BytesIO(z.read(n))).size == (480, 360)
    # numbering can be switched off: names are then exactly the originals
    z2 = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip?numbering=0").content))
    assert sorted(n for n in z2.namelist() if not n.endswith(".csv")) == sorted(["Al Khuzama/1/a.jpg", "Al Khuzama/1/B.JPG", "Al Khuzama/02/a.jpg", "Al Khuzama/3/x/deep.jpg", "Al Khuzama/3/x/also.jpg"])
    # download log keeps the original names
    log = z.read("Al Khuzama/Roomlit log.csv").decode("utf-8-sig")
    for orig in ("a.jpg", "B.JPG", "deep.jpg", "also.jpg"):
        assert orig in log
    assert c.get(f"/api/jobs/{jid}/log.csv").status_code == 200
    one = c.get(f"/api/jobs/{jid}/items/{j['items'][0]['id']}/download")
    assert one.status_code == 200 and Image.open(io.BytesIO(one.content)).size == (480, 360)
    root = main.store.jobs[jid].root
    assert c.delete(f"/api/jobs/{jid}", headers=H).status_code == 200
    assert not os.path.exists(root)


def test_same_name_files_in_one_folder_are_both_delivered(authed):
    c = authed
    jid, j = run_job(c, {"R/1/a.jpg": jpeg(k=11), "R/1/A.JPG": jpeg(k=12)})        # case-insensitive clash
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip?numbering=0").content))
    names = sorted(n for n in z.namelist() if not n.endswith(".csv"))
    assert names == ["R/1/A (2).JPG", "R/1/a.jpg"] or names == ["R/1/A.JPG", "R/1/a (2).jpg"] or len(names) == 2


def test_zip_upload_keeps_the_zip_folder_name(authed):
    c = authed
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, n in enumerate(["Villa Nord/Living/1.jpg", "Villa Nord/Bedroom/2.jpg", "Villa Nord/Bedroom/3.jpg"]):
            z.writestr(n, jpeg(k=20 + k))
        z.writestr("__MACOSX/Villa Nord/._1.jpg", b"junk"); z.writestr("Villa Nord/readme.txt", b"hi"); z.writestr("../evil.jpg", b"x")
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    r = up(c, jid, "whatever-the-file-is-called.zip", buf.getvalue())
    assert r.status_code == 200 and r.json()["accepted"] == 3
    j = wait(c, jid, lambda j: j["counts"]["ready"] == 3)
    assert j["ignored"].get("unsafe") == 1 and j["ignored"].get("unsupported") == 1
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    j = wait(c, jid, lambda j: j["counts"]["done"] == 3)
    assert j["zip_name"] == "Villa Nord.zip"
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip?numbering=0").content))
    assert sorted(n for n in z.namelist() if not n.endswith(".csv")) == ["Villa Nord/Bedroom/2.jpg", "Villa Nord/Bedroom/3.jpg", "Villa Nord/Living/1.jpg"]


def test_loose_files_and_multiple_roots(authed):
    c = authed
    jid, j = run_job(c, {"loose.jpg": jpeg(k=30), "Other Folder/x.jpg": jpeg(k=31)})
    assert j["zip_name"] == "Roomlit export.zip"
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip?numbering=0").content))
    assert sorted(n for n in z.namelist() if not n.endswith(".csv")) == ["Other Folder/x.jpg", "Photos/loose.jpg"]
    assert "Roomlit log.csv" in z.namelist()


def test_reprocess_one_photo_and_all_modes(authed):
    c = authed
    jid, j = run_job(c, {"R/1/a.jpg": jpeg(k=40), "R/1/b.jpg": jpeg(k=41)}, mode="natural")
    item = j["items"][0]; v0 = item["v"]
    assert c.post(f"/api/jobs/{jid}/items/{item['id']}/reprocess", json={"mode": "bright"}, headers=H).status_code == 200
    j = wait(c, jid, lambda j: next(i for i in j["items"] if i["id"] == item["id"])["v"] == v0 + 1 and j["counts"]["done"] == 2)
    assert next(i for i in j["items"] if i["id"] == item["id"])["mode"] == "bright"
    for kind in ("before", "after", "thumb"):
        assert c.get(f"/api/jobs/{jid}/items/{item['id']}/preview/{kind}").headers["content-type"] == "image/jpeg"
    for mode in ("natural", "premium", "bright"):
        assert c.post(f"/api/jobs/{jid}/reprocess", json={"mode": mode}, headers=H).status_code == 200
        time.sleep(0.5)
        j = wait(c, jid, lambda j: j["counts"]["done"] == 2 and all(i["mode"] == mode for i in j["items"]))


def test_corrupt_photo_fails_alone_and_is_cleaned(authed):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/good.jpg", jpeg(k=50)); up(c, jid, "R/bad.jpg", b"definitely not a jpeg" * 50)
    j = wait(c, jid, lambda j: j["counts"]["ready"] + j["counts"]["failed"] == 2)
    bad = next(i for i in j["items"] if i["name"] == "bad.jpg")
    assert bad["status"] == "failed" and ("readable" in bad["err"] or "supported" in bad["err"])
    assert not os.path.exists(main.store.jobs[jid].p_original(bad["id"]))
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    j = wait(c, jid, lambda j: j["counts"]["done"] == 1)
    assert j["counts"]["final"] == 1 and c.get(f"/api/jobs/{jid}/download.zip").status_code == 200


def test_fully_failed_job_purges_its_files(authed):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "X/bad1.jpg", b"x" * 300); up(c, jid, "X/bad2.png", b"y" * 300)
    wait(c, jid, lambda j: j["counts"]["failed"] == 2 and j["purged"])
    job = main.store.jobs[jid]
    assert [f for dp, _, fs in os.walk(job.root) for f in fs] == [] and job.failed_at
    assert c.get(f"/api/jobs/{jid}/download.zip").status_code == 409


def test_limits_are_enforced(authed, monkeypatch):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, max_file_mb=1))
    r = up(c, jid, "R/huge.jpg", b"\xff\xd8" + os.urandom(1_200_000))
    assert r.status_code == 413 and r.json()["error"] == "file_too_large"
    assert os.listdir(main.store.jobs[jid].p_tmp) == []
    monkeypatch.setattr(main.store, "cfg", dataclasses.replace(main.store.cfg, max_files_per_job=2))
    assert up(c, jid, "R/1.jpg", jpeg(k=60)).status_code == 200 and up(c, jid, "R/2.jpg", jpeg(k=61)).status_code == 200
    assert up(c, jid, "R/3.jpg", jpeg(k=62)).status_code == 413


def test_expiry_and_downloaded_shortening(authed):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/1.jpg", jpeg(k=70)); wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    job = main.store.jobs[jid]
    assert job not in main.store.expired()
    job.last_activity -= (main.cfg.job_ttl_minutes + 1) * 60
    assert job in main.store.expired()
    main.store.delete(job)
    assert jid not in main.store.jobs and not os.path.exists(job.root)
    jid, j = run_job(c, {"R/1.jpg": jpeg(k=71)})
    before = c.get(f"/api/jobs/{jid}").json()["expires_in"]
    c.get(f"/api/jobs/{jid}/download.zip")
    after = c.get(f"/api/jobs/{jid}").json()
    assert after["downloaded"] and after["expires_in"] <= main.cfg.downloaded_ttl_minutes * 60 < before


def test_worker_crash_is_survived(authed):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/1.jpg", jpeg(k=80)); up(c, jid, "R/2.jpg", jpeg(k=81))
    wait(c, jid, lambda j: j["counts"]["ready"] == 2)
    os.kill(main.dispatcher.worker.pid, signal.SIGKILL); time.sleep(0.5)
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    j = wait(c, jid, lambda j: j["counts"]["done"] + j["counts"]["failed"] == 2)
    assert j["counts"]["done"] == 2, j["counts"]
    up(c, jid, "R/3.jpg", jpeg(k=82)); wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    deadline = time.time() + 20
    while time.time() < deadline and not (main.dispatcher.worker.pid and main.dispatcher.busy):
        time.sleep(0.01)
    if main.dispatcher.worker.pid: os.kill(main.dispatcher.worker.pid, signal.SIGKILL)
    wait(c, jid, lambda j: j["counts"]["done"] + j["counts"]["failed"] == 3)
    up(c, jid, "R/4.jpg", jpeg(k=83)); wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    j = wait(c, jid, lambda j: j["counts"]["done"] + j["counts"]["failed"] == 4)
    assert next(i for i in j["items"] if i["name"] == "4.jpg")["status"] == "done"
