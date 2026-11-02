import dataclasses, glob, io, os, time, zipfile
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
    r = client.post("/api/login", json={"username": "admin", "password": "test-password"}, headers=H)
    assert r.status_code == 200
    yield client
    for j in client.get("/api/jobs").json().get("jobs", []):
        client.delete(f"/api/jobs/{j['id']}", headers=H)


def jpeg(tmp_path, name="p.jpg", **kw):
    p = tmp_path / name; synth.save_jpeg(str(p), synth.scene(w=480, h=360, **kw)); return p.read_bytes()


def up(c, jid, path, data, headers=FILE):
    return c.post(f"/api/jobs/{jid}/files", params={"path": path}, content=data, headers=headers)


def wait(c, jid, pred, t=120):
    end = time.time() + t
    while time.time() < end:
        j = c.get(f"/api/jobs/{jid}").json()
        if pred(j): return j
        time.sleep(0.2)
    raise AssertionError(j)


# ---------------------------------------------------------------- security
def test_everything_requires_login(client):
    client.cookies.clear()
    for method, path in [("get", "/api/jobs"), ("get", "/api/config"), ("get", "/api/diag"), ("post", "/api/jobs"),
                         ("get", "/api/jobs/abc"), ("get", "/api/jobs/abc/items/1/preview/before"), ("get", "/api/jobs/abc/download.zip")]:
        r = getattr(client, method)(path, headers=H)
        assert r.status_code == 401, path
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/").status_code == 200                      # the app shell itself holds no photos


def test_wrong_password_and_lockout(client):
    client.cookies.clear()
    main.auth._fails.clear(); main.auth._locked.clear()
    for _ in range(5):
        assert client.post("/api/login", json={"username": "admin", "password": "nope"}, headers=H).status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "nope"}, headers=H).status_code == 401   # 6th failure arms the lock
    r = client.post("/api/login", json={"username": "admin", "password": "test-password"}, headers=H)
    assert r.status_code == 429                                    # even the right password is refused while locked
    main.auth._fails.clear(); main.auth._locked.clear()


def test_csrf_header_required_and_cookie_flags(client):
    main.auth._fails.clear(); main.auth._locked.clear()
    r = client.post("/api/login", json={"username": "admin", "password": "test-password"})
    assert r.status_code == 403                                    # no custom header -> blocked
    r = client.post("/api/login", json={"username": "admin", "password": "test-password"}, headers={**H, "Origin": "https://evil.example"})
    assert r.status_code == 403                                    # foreign origin -> blocked
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
    assert up(c, jid, "../../evil.jpg", jpeg(tmp_path)).status_code == 400
    assert up(c, jid, "/etc/passwd.jpg", jpeg(tmp_path)).status_code == 400
    assert c.get("/api/jobs/..%2f..%2fetc/items/1/preview/before").status_code in (401, 404)
    assert c.get(f"/api/jobs/{jid}/items/1/preview/../../../x").status_code in (404, 405)
    assert c.get(f"/api/jobs/{jid}/items/999/preview/before").status_code == 404
    assert c.get("/api/jobs/does-not-exist").status_code == 404


# ---------------------------------------------------------------- end to end
def test_folder_upload_process_zip_structure_names_and_dims(authed, tmp_path):
    c = authed
    jid = c.post("/api/jobs", json={"mode": "premium"}, headers=H).json()["id"]
    data = jpeg(tmp_path)
    for rel in ["Photos Al Khuzama/1/a.jpg", "Photos Al Khuzama/1/B.JPG", "Photos Al Khuzama/02/a.jpg", "Photos Al Khuzama/3/x/deep.jpg",
                "Photos Al Khuzama/1/a.jpg"]:                       # last one is a duplicate name
        assert up(c, jid, rel, data).json()["accepted"] == 1
    assert up(c, jid, "Photos Al Khuzama/1/notes.txt", b"hi").json()["ignored"] == 1      # unsupported -> ignored
    assert up(c, jid, "Photos Al Khuzama/.DS_Store", b"x").json() == {"accepted": 0, "ignored": 0}
    j = wait(c, jid, lambda j: j["counts"]["ready"] == 5)
    assert j["ignored"]["unsupported"] == 1
    assert c.post(f"/api/jobs/{jid}/start", json={"mode": "bright"}, headers=H).json()["queued"] == 5
    j = wait(c, jid, lambda j: j["counts"]["done"] == 5)
    r = c.get(f"/api/jobs/{jid}/download.zip")
    assert r.status_code == 200 and "Photos%20Al%20Khuzama%20-%20Edited.zip" in r.headers["content-disposition"].replace("'", "").replace("filename*=utf-8", "")  or "Edited.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == sorted([
        "Photos Al Khuzama - Edited/1/Edited - Airbnb/a.jpg", "Photos Al Khuzama - Edited/1/Edited - Airbnb/a (2).jpg",
        "Photos Al Khuzama - Edited/1/Edited - Airbnb/B.JPG", "Photos Al Khuzama - Edited/02/Edited - Airbnb/a.jpg",
        "Photos Al Khuzama - Edited/3/x/Edited - Airbnb/deep.jpg"])
    for n in z.namelist():
        assert Image.open(io.BytesIO(z.read(n))).size == (480, 360)           # dimensions preserved
    one = c.get(f"/api/jobs/{jid}/items/{j['items'][0]['id']}/download")
    assert one.status_code == 200 and Image.open(io.BytesIO(one.content)).size == (480, 360)
    for kind in ("before", "after", "thumb"):
        assert c.get(f"/api/jobs/{jid}/items/{j['items'][0]['id']}/preview/{kind}").headers["content-type"] == "image/jpeg"
    # reprocess one photo in another mode
    iid = j["items"][0]["id"]; v0 = j["items"][0]["v"]
    assert c.post(f"/api/jobs/{jid}/items/{iid}/reprocess", json={"mode": "natural"}, headers=H).status_code == 200
    j = wait(c, jid, lambda j: all(i["status"] == "done" for i in j["items"]) and next(i for i in j["items"] if i["id"] == iid)["v"] == v0 + 1)
    assert next(i for i in j["items"] if i["id"] == iid)["mode"] == "natural"
    # delete -> everything gone from disk
    root = main.store.jobs[jid].root
    assert os.path.isdir(root)
    assert c.delete(f"/api/jobs/{jid}", headers=H).status_code == 200
    assert not os.path.exists(root)
    assert c.get(f"/api/jobs/{jid}").status_code == 404


def test_zip_upload_end_to_end(authed, tmp_path):
    c = authed
    data = jpeg(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in ["Villa Nord/Living/1.jpg", "Villa Nord/Bedroom/2.jpg", "Villa Nord/Bedroom/3.jpg", "__MACOSX/Villa Nord/._1.jpg", "Villa Nord/readme.txt", "../evil.jpg"]:
            z.writestr(n, data if n.endswith(".jpg") else b"text")
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    r = up(c, jid, "Villa Nord.zip", buf.getvalue())
    assert r.status_code == 200 and r.json()["accepted"] == 3, r.text
    j = wait(c, jid, lambda j: j["counts"]["ready"] == 3)
    assert j["ignored"].get("unsafe") == 1 and j["ignored"].get("unsupported") == 1
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    wait(c, jid, lambda j: j["counts"]["done"] == 3)
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip").content))
    assert sorted(z.namelist()) == ["Villa Nord - Edited/Bedroom/Edited - Airbnb/2.jpg", "Villa Nord - Edited/Bedroom/Edited - Airbnb/3.jpg", "Villa Nord - Edited/Living/Edited - Airbnb/1.jpg"]


def test_corrupt_photo_fails_alone_and_is_cleaned(authed, tmp_path):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/good.jpg", jpeg(tmp_path)); up(c, jid, "R/bad.jpg", b"definitely not a jpeg" * 50)
    j = wait(c, jid, lambda j: j["counts"]["ready"] + j["counts"]["failed"] == 2)
    assert j["counts"] == {**j["counts"], "ready": 1, "failed": 1}
    bad = next(i for i in j["items"] if i["name"] == "bad.jpg")
    assert "readable" in bad["err"] or "supported" in bad["err"]
    assert not os.path.exists(main.store.jobs[jid].p_original(bad["id"]))      # the broken upload is deleted at once
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    wait(c, jid, lambda j: j["counts"]["done"] == 1)
    assert c.get(f"/api/jobs/{jid}/download.zip").status_code == 200           # the good photo is still delivered


def test_fully_failed_job_purges_its_files(authed, tmp_path):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/bad1.jpg", b"x" * 300); up(c, jid, "R/bad2.png", b"y" * 300)
    j = wait(c, jid, lambda j: j["counts"]["failed"] == 2 and j["purged"])
    job = main.store.jobs[jid]
    left = [f for dp, _, fs in os.walk(job.root) for f in fs]
    assert left == [] and job.failed_at
    assert c.get(f"/api/jobs/{jid}/download.zip").status_code == 409


def test_limits_are_enforced(authed, tmp_path, monkeypatch):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, max_file_mb=1))
    r = up(c, jid, "R/huge.jpg", b"\xff\xd8" + os.urandom(1_200_000))
    assert r.status_code == 413 and r.json()["error"] == "file_too_large"
    assert os.listdir(main.store.jobs[jid].p_tmp) == []                        # the partial upload was removed
    monkeypatch.setattr(main.store, "cfg", dataclasses.replace(main.store.cfg, max_files_per_job=2))
    data = jpeg(tmp_path)
    assert up(c, jid, "R/1.jpg", data).status_code == 200 and up(c, jid, "R/2.jpg", data).status_code == 200
    assert up(c, jid, "R/3.jpg", data).status_code == 413


def test_expiry_and_downloaded_shortening(authed, tmp_path):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/1.jpg", jpeg(tmp_path)); wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    job = main.store.jobs[jid]
    assert main.store.expired() == [] or job not in main.store.expired()
    job.last_activity -= (main.cfg.job_ttl_minutes + 1) * 60                   # abandoned
    assert job in main.store.expired()
    main.store.delete(job)
    assert jid not in main.store.jobs and not os.path.exists(job.root)
    # after a completed download the retention window shrinks
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/1.jpg", jpeg(tmp_path)); wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H); wait(c, jid, lambda j: j["counts"]["done"] == 1)
    before = c.get(f"/api/jobs/{jid}").json()["expires_in"]
    c.get(f"/api/jobs/{jid}/download.zip")
    after = c.get(f"/api/jobs/{jid}").json()
    assert after["downloaded"] and after["expires_in"] <= main.cfg.downloaded_ttl_minutes * 60 < before


def test_worker_crash_is_survived(authed, tmp_path):
    """Kill the worker mid-queue: the photo is reported failed, the worker restarts, the next photo works."""
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/1.jpg", jpeg(tmp_path)); up(c, jid, "R/2.jpg", jpeg(tmp_path, seed=3))
    wait(c, jid, lambda j: j["counts"]["ready"] == 2)
    pid = main.dispatcher.worker.pid
    import signal; os.kill(pid, signal.SIGKILL); time.sleep(0.5)
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    j = wait(c, jid, lambda j: j["counts"]["done"] + j["counts"]["failed"] == 2)
    assert j["counts"]["done"] == 2, j["counts"]                              # a dead idle worker is simply replaced
    # now simulate dying *during* a task
    up(c, jid, "R/3.jpg", jpeg(tmp_path, seed=4)); wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    deadline = time.time() + 20
    while time.time() < deadline and not (main.dispatcher.worker.pid and main.dispatcher.busy):
        time.sleep(0.01)
    if main.dispatcher.worker.pid: os.kill(main.dispatcher.worker.pid, signal.SIGKILL)
    j = wait(c, jid, lambda j: j["counts"]["done"] + j["counts"]["failed"] == 3)
    up(c, jid, "R/4.jpg", jpeg(tmp_path, seed=5)); wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    j = wait(c, jid, lambda j: j["counts"]["done"] + j["counts"]["failed"] == 4)
    assert next(i for i in j["items"] if i["name"] == "4.jpg")["status"] == "done"
