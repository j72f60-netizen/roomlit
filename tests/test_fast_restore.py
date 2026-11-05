"""Set-aside photos are edited quietly in the background, so Restore (and the promotion of a twin) is instant."""
import asyncio, io, time, zipfile
import pytest
import app.main as main
from app.runner import Dispatcher
from .test_api import H, up, wait, client, authed  # noqa: F401
from .test_organize_api import build_files


def start_smart_job(c):
    files = build_files()
    jid = c.post("/api/jobs", json={"mode": "premium"}, headers=H).json()["id"]
    for p, d in files.items():
        assert up(c, jid, p, d).status_code == 200
    wait(c, jid, lambda j: j["counts"]["ready"] == len(files))
    assert c.post(f"/api/jobs/{jid}/start", json={"mode": "premium", "smart": True}, headers=H).status_code == 200
    j = wait(c, jid, lambda j: j["phase"] == "done")
    return jid, j


def wait_preedited(jid, timeout=120):
    job = main.store.jobs[jid]
    end = time.time() + timeout
    while time.time() < end:
        aside = [i for i in job.items.values() if i.excluded and i.status == "ready"]
        if aside and all(i.pre is not None for i in aside):
            return aside
        time.sleep(0.3)
    raise AssertionError("background edits did not finish")


def test_restoring_a_set_aside_photo_is_instant_because_it_was_edited_in_the_background(authed):
    c = authed
    jid, j = start_smart_job(c)
    aside = wait_preedited(jid)
    assert all(i.status == "ready" for i in aside)                                   # still set aside: not part of the delivery
    assert j["counts"]["done"] == 6 and j["counts"]["excluded"] == 3
    victim = aside[0]
    t0 = time.time()
    assert c.post(f"/api/jobs/{jid}/items/{victim.id}/restore", headers=H).status_code == 200
    now = c.get(f"/api/jobs/{jid}").json()                                           # no waiting: it is already edited
    assert time.time() - t0 < 1.5
    it = next(i for i in now["items"] if i["id"] == victim.id)
    assert it["status"] == "done" and it["ex"] is False and it["pos"] > 0 and it["v"] >= 1
    assert now["counts"]["done"] == 7 and now["counts"]["excluded"] == 2 and now["counts"]["queued"] == 0
    names = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip?numbering=0&suffix=").content)).namelist()
    assert len(names) == 7 and any(n.endswith("/" + victim.name) for n in names)
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_excluding_the_best_copy_promotes_an_already_edited_twin_at_once(authed):
    c = authed
    jid, j = start_smart_job(c)
    wait_preedited(jid)
    job = main.store.jobs[jid]
    keeper = next(i for i in job.items.values() if i.status == "done" and any(o.dup_of == i.id for o in job.items.values()))
    assert c.post(f"/api/jobs/{jid}/items/{keeper.id}/exclude", headers=H).status_code == 200
    now = c.get(f"/api/jobs/{jid}").json()
    assert now["counts"]["queued"] == 0 and now["counts"]["processing"] == 0                  # the twin did not need editing
    assert now["counts"]["done"] == 7 and now["counts"]["final"] == 6
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_a_stale_background_edit_is_not_used(authed):
    c = authed
    jid, _ = start_smart_job(c)
    aside = wait_preedited(jid)
    v = aside[0]
    assert c.post(f"/api/jobs/{jid}/items/{v.id}/retouch",
                  json={"ops": [{"t": "remove", "r": 0.02, "pts": [[0.5, 0.5]]}]}, headers=H).status_code == 200
    assert main.store.jobs[jid].items[v.id].pre is None                                       # strokes changed: the old edit is void
    assert c.post(f"/api/jobs/{jid}/items/{v.id}/restore", headers=H).status_code == 200
    j = wait(c, jid, lambda j: j["counts"]["done"] == 7)                                      # edited again, with the strokes
    assert next(i for i in j["items"] if i["id"] == v.id)["rt"] == 1
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_user_work_always_jumps_ahead_of_background_edits():
    async def go():
        d = Dispatcher.__new__(Dispatcher)
        import itertools
        d.queue = asyncio.PriorityQueue(); d._seq = itertools.count()
        order = []
        d._put(1, "preedit", "job", 1, "pro"); d._put(1, "preedit", "job", 2, "pro")
        d._put(0, "analyze", "job", 3, None); d._put(0, "process", "job", 4, "pro")
        while not d.queue.empty():
            _, _, kind, _, iid, _ = d.queue.get_nowait(); order.append((kind, iid))
        return order
    assert asyncio.run(go()) == [("analyze", 3), ("process", 4), ("preedit", 1), ("preedit", 2)]


def test_a_restored_photo_goes_back_to_where_it_stood(authed):
    c = authed
    jid, j = start_smart_job(c)
    s = next(x for x in j["sets"] if x["label"] == "1")
    order = list(s["order"])
    gone = order[2]
    assert c.post(f"/api/jobs/{jid}/items/{gone}/exclude", headers=H).status_code == 200
    mid = next(x for x in c.get(f"/api/jobs/{jid}").json()["sets"] if x["id"] == s["id"])["order"]
    assert gone not in mid
    assert c.post(f"/api/jobs/{jid}/items/{gone}/restore", headers=H).status_code == 200
    back = next(x for x in c.get(f"/api/jobs/{jid}").json()["sets"] if x["id"] == s["id"])["order"]
    assert back.index(gone) == 2 and [i for i in back if i != gone] == [i for i in order if i != gone]
    c.delete(f"/api/jobs/{jid}", headers=H)
