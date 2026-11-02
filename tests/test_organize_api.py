"""The arrange-before-download workflow through the real API (upload -> organise -> edit -> review -> download)."""
import dataclasses, io, os, time, zipfile
import cv2
import pytest
from fastapi.testclient import TestClient
import app.main as main
from . import synth
from .test_api import H, FILE, up, wait, jpeg, run_job, client, authed  # noqa: F401


def enc(img, q=92) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()


def build_files():
    a, b, c_ = synth.layout(201), synth.layout(202), synth.layout(203)
    return {
        # apartment 1: A shot three times (original, much darker+warm, small low-quality), B, and C from two real angles
        "Al Khuzama/1/IMG_001.jpg": enc(a), "Al Khuzama/1/IMG_002.jpg": enc(synth.relit(a, 1.7, 0.7, (1.1, 1.0, 0.9))),
        "Al Khuzama/1/other name.jpg": enc(synth.resized_q(a, 0.5, 60)),
        "Al Khuzama/1/IMG_003.jpg": enc(b), "Al Khuzama/1/IMG_004.jpg": enc(c_), "Al Khuzama/1/IMG_005.jpg": enc(synth.other_angle(c_)),
        # apartment 02 has the SAME photo A plus its own copy and a different photo: apartments are never merged
        "Al Khuzama/02/x1.jpg": enc(a), "Al Khuzama/02/x2.jpg": enc(synth.relit(a, 0.6, 1.0, (0.95, 1, 1.05))), "Al Khuzama/02/x3.jpg": enc(synth.layout(204)),
    }


@pytest.fixture
def job(authed):
    c = authed
    jid, j = run_job(c, build_files())
    yield c, jid, j
    c.delete(f"/api/jobs/{jid}", headers=H)


def by_name(j, folder):
    return {i["name"]: i for i in j["items"] if i["dir"].endswith(folder)}


def zip_names(c, jid, numbering=1):
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{jid}/download.zip?numbering={numbering}").content))
    return z, [n for n in z.namelist() if not n.endswith(".csv")]


def test_duplicates_are_found_and_listed_but_not_edited(job):
    c, jid, j = job
    one, two = by_name(j, "/1"), by_name(j, "/02")
    dups1 = [n for n, i in one.items() if i["ex"]]
    assert len(dups1) == 2 and all(one[n]["ex_why"] == "dup" for n in dups1)                       # darker copy + small copy
    assert one["IMG_003.jpg"]["ex"] is False and one["IMG_004.jpg"]["ex"] is False and one["IMG_005.jpg"]["ex"] is False   # other room / other angles kept
    keeper1 = [n for n, i in one.items() if n in ("IMG_001.jpg", "IMG_002.jpg", "other name.jpg") and not i["ex"]]
    assert len(keeper1) == 1 and one[keeper1[0]]["pos"] >= 1
    for n in dups1:
        assert one[n]["dup_of"] == one[keeper1[0]]["id"]
        assert one[n]["status"] == "ready" and one[n]["pos"] == 0                                    # kept on the server, not edited
    assert [n for n, i in two.items() if i["ex"]].__len__() == 1 and two["x3.jpg"]["ex"] is False   # apartment 02 judged on its own
    cnt = j["counts"]
    assert (cnt["total"], cnt["excluded"], cnt["final"], cnt["done"]) == (9, 3, 6, 6)
    assert [s["label"] for s in j["sets"]] == ["02", "1"] or {s["label"] for s in j["sets"]} == {"1", "02"}
    assert all(i["pos"] == 0 for i in j["items"] if i["ex"])


def test_apartments_are_ordered_independently(job):
    c, jid, j = job
    s = {x["label"]: x for x in j["sets"]}
    ids1 = {i["id"] for i in j["items"] if i["dir"].endswith("/1")}
    ids2 = {i["id"] for i in j["items"] if i["dir"].endswith("/02")}
    assert set(s["1"]["order"]) <= ids1 and set(s["02"]["order"]) <= ids2
    assert len(s["1"]["order"]) == 4 and len(s["02"]["order"]) == 2
    assert all(x["organized"] for x in s.values())


def test_zip_contains_only_kept_photos_in_order_and_log_explains_the_rest(job):
    c, jid, j = job
    z, names = zip_names(c, jid)
    assert len(names) == 6 and all(n.startswith("Al Khuzama/") for n in names)
    one = [n for n in names if n.startswith("Al Khuzama/1/")]
    assert sorted(os.path.basename(n)[:2] for n in one) == ["01", "02", "03", "04"]
    first = sorted(one)[0]
    s1 = next(s for s in j["sets"] if s["label"] == "1")
    main_item = next(i for i in j["items"] if i["id"] == s1["order"][0])
    assert first.endswith(" - " + main_item["name"])                                                # file 01 is the chosen main photo
    log = z.read("Al Khuzama/Roomlit log.csv").decode("utf-8-sig")
    rows = [r.split(",") for r in log.strip().splitlines()[1:]]
    assert sum(1 for r in rows if "excluded" in r) == 3
    assert "Same shot as" in log and all(n in log for n in ("IMG_001.jpg", "IMG_002.jpg", "other name.jpg", "x1.jpg", "x2.jpg"))
    assert "main_photo" in log and "yes" in log


def test_excluded_photos_stay_on_the_server_until_the_job_is_deleted(job):
    c, jid, j = job
    ex = [i for i in j["items"] if i["ex"]]
    jb = main.store.jobs[jid]
    assert ex and all(os.path.exists(jb.p_original(i["id"])) for i in ex)
    assert all(c.get(f"/api/jobs/{jid}/items/{i['id']}/preview/before").status_code == 200 for i in ex)
    c.get(f"/api/jobs/{jid}/download.zip")                                                          # downloading does not drop them either
    assert all(os.path.exists(jb.p_original(i["id"])) for i in ex)
    root = jb.root
    c.delete(f"/api/jobs/{jid}", headers=H)
    assert not os.path.exists(root)


def test_restore_an_excluded_photo_edits_it_and_puts_it_next_to_its_twin(job):
    c, jid, j = job
    one = by_name(j, "/1")
    dup = next(i for i in one.values() if i["ex"])
    twin = next(i for i in one.values() if i["id"] == dup["dup_of"])
    assert c.post(f"/api/jobs/{jid}/items/{dup['id']}/restore", headers=H).status_code == 200
    j = wait(c, jid, lambda j: next(i for i in j["items"] if i["id"] == dup["id"])["status"] == "done")
    one = by_name(j, "/1")
    d = next(i for i in one.values() if i["id"] == dup["id"]); t = next(i for i in one.values() if i["id"] == twin["id"])
    assert d["ex"] is False and d["restored"] is True and d["pos"] == t["pos"] + 1
    assert (j["counts"]["excluded"], j["counts"]["final"]) == (2, 7)
    z, names = zip_names(c, jid)
    assert len([n for n in names if n.startswith("Al Khuzama/1/")]) == 5 and len(names) == 7


def test_user_can_exclude_and_bring_back_a_kept_photo(job):
    c, jid, j = job
    it = by_name(j, "/1")["IMG_003.jpg"]
    assert c.post(f"/api/jobs/{jid}/items/{it['id']}/exclude", headers=H).status_code == 200
    j = c.get(f"/api/jobs/{jid}").json()
    now = by_name(j, "/1")["IMG_003.jpg"]
    assert now["ex"] and now["ex_why"] == "user" and now["pos"] == 0 and j["counts"]["final"] == 5
    _, names = zip_names(c, jid); assert not any(n.endswith("IMG_003.jpg") for n in names)
    assert c.post(f"/api/jobs/{jid}/items/{it['id']}/restore", headers=H).status_code == 200
    j = c.get(f"/api/jobs/{jid}").json()
    assert by_name(j, "/1")["IMG_003.jpg"]["pos"] >= 1 and j["counts"]["final"] == 6
    _, names = zip_names(c, jid); assert any(n.endswith("IMG_003.jpg") for n in names)


def test_excluding_the_best_copy_promotes_its_twin_so_the_angle_is_not_lost(job):
    c, jid, j = job
    one = by_name(j, "/1")
    keeper = next(i for i in one.values() if i["name"] in ("IMG_001.jpg", "IMG_002.jpg", "other name.jpg") and not i["ex"])
    assert c.post(f"/api/jobs/{jid}/items/{keeper['id']}/exclude", headers=H).status_code == 200
    j = wait(c, jid, lambda j: sum(1 for i in j["items"] if i["dir"].endswith("/1") and i["name"] in ("IMG_001.jpg", "IMG_002.jpg", "other name.jpg") and i["status"] == "done" and not i["ex"]) == 1
             and j["counts"]["queued"] + j["counts"]["processing"] == 0)
    kept = [i for i in by_name(j, "/1").values() if i["name"] in ("IMG_001.jpg", "IMG_002.jpg", "other name.jpg") and not i["ex"]]
    assert len(kept) == 1 and kept[0]["id"] != keeper["id"]                                         # a twin took over (and was edited)
    assert len(next(s for s in j["sets"] if s["label"] == "1")["order"]) == 4


def test_drag_and_drop_order_is_applied_to_the_zip(job):
    c, jid, j = job
    s = next(x for x in j["sets"] if x["label"] == "1")
    new = list(reversed(s["order"]))
    assert c.post(f"/api/jobs/{jid}/sets/{s['id']}/order", json={"order": new}, headers=H).status_code == 200
    j2 = c.get(f"/api/jobs/{jid}").json()
    assert next(x for x in j2["sets"] if x["label"] == "1")["order"] == new and next(x for x in j2["sets"] if x["label"] == "1")["manual"] is True
    pos = {i["id"]: i["pos"] for i in j2["items"]}
    assert [pos[i] for i in new] == [1, 2, 3, 4]
    z, names = zip_names(c, jid)
    one = sorted(n for n in names if n.startswith("Al Khuzama/1/"))
    items = {i["id"]: i["name"] for i in j2["items"]}
    assert [n.split(" - ", 1)[1] for n in one] == [items[i] for i in new]                           # file order = dragged order
    # other apartment untouched
    s2 = next(x for x in j["sets"] if x["label"] == "02"); assert next(x for x in j2["sets"] if x["label"] == "02")["order"] == s2["order"]
    # a stale / forged order is refused
    assert c.post(f"/api/jobs/{jid}/sets/{s['id']}/order", json={"order": new[:-1]}, headers=H).status_code == 409
    assert c.post(f"/api/jobs/{jid}/sets/{s['id']}/order", json={"order": new + [s2["order"][0]]}, headers=H).status_code == 409
    assert c.post(f"/api/jobs/{jid}/sets/{s['id']}/order", json={"order": "x"}, headers=H).status_code == 400
    # reset goes back to a suggested order
    assert c.post(f"/api/jobs/{jid}/sets/{s['id']}/reset-order", headers=H).status_code == 200
    j3 = c.get(f"/api/jobs/{jid}").json(); assert next(x for x in j3["sets"] if x["label"] == "1")["manual"] is False


def test_choose_a_different_main_photo(job):
    c, jid, j = job
    s = next(x for x in j["sets"] if x["label"] == "1")
    pick = s["order"][-1]
    assert c.post(f"/api/jobs/{jid}/items/{pick}/main", headers=H).status_code == 200
    j2 = c.get(f"/api/jobs/{jid}").json()
    assert next(x for x in j2["sets"] if x["label"] == "1")["order"][0] == pick
    z, names = zip_names(c, jid)
    first = sorted(n for n in names if n.startswith("Al Khuzama/1/"))[0]
    assert first.endswith(" - " + next(i["name"] for i in j2["items"] if i["id"] == pick))
    excl = next(i for i in j2["items"] if i["ex"])
    assert c.post(f"/api/jobs/{jid}/items/{excl['id']}/main", headers=H).status_code == 409        # must be restored first


def test_room_label_can_be_corrected_and_is_kept_in_the_log(job):
    c, jid, j = job
    it = next(i for i in j["items"] if not i["ex"])
    assert c.post(f"/api/jobs/{jid}/items/{it['id']}/room", json={"room": "kitchen"}, headers=H).status_code == 200
    assert c.post(f"/api/jobs/{jid}/items/{it['id']}/room", json={"room": "spaceship"}, headers=H).status_code == 400
    j2 = c.get(f"/api/jobs/{jid}").json(); i2 = next(i for i in j2["items"] if i["id"] == it["id"])
    assert i2["room"] == "kitchen" and i2["room_user"] is True and i2["room_sure"] is True
    log = c.get(f"/api/jobs/{jid}/log.csv").content.decode("utf-8-sig")
    assert "kitchen" in log and "yes" in log


def test_adding_photos_later_keeps_the_users_arrangement(job):
    c, jid, j = job
    s = next(x for x in j["sets"] if x["label"] == "1")
    new = list(reversed(s["order"]))
    c.post(f"/api/jobs/{jid}/sets/{s['id']}/order", json={"order": new}, headers=H)
    assert up(c, jid, "Al Khuzama/1/late.jpg", enc(synth.layout(299))).status_code == 200
    wait(c, jid, lambda j: j["counts"]["ready"] >= 1 and j["counts"]["uploaded"] + j["counts"]["analyzing"] == 0)
    assert c.post(f"/api/jobs/{jid}/start", json={}, headers=H).status_code == 200
    j2 = wait(c, jid, lambda j: j["phase"] == "done")
    order = next(x for x in j2["sets"] if x["label"] == "1")["order"]
    assert order[:4] == new and len(order) == 5                                                    # arranged photos did not move; new one appended


def test_without_the_room_model_everything_is_kept_in_upload_order(authed, monkeypatch, tmp_path):
    c = authed
    monkeypatch.setattr(main.dispatcher, "cfg", dataclasses.replace(main.dispatcher.cfg, model_dir=str(tmp_path / "nomodel")))
    a = synth.layout(301)
    jid, j = run_job(c, {"R/1/a.jpg": enc(a), "R/1/a copy.jpg": enc(a), "R/1/b.jpg": enc(synth.layout(302))})
    # exact duplicates are still found by geometry; labels are simply unknown (user can set them)
    assert j["counts"]["excluded"] == 1 and j["counts"]["final"] == 2
    assert all(i["room"] in (None, "other") for i in j["items"] if not i["ex"])
    assert c.get(f"/api/jobs/{jid}/download.zip").status_code == 200
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_organizer_failure_never_blocks_editing(authed, monkeypatch):
    c = authed
    import app.runner as runner
    original = runner.WorkerProc.call

    def call(self, fn, args, timeout):
        if self.kind == "ml":
            raise runner.WorkerError("simulated organizer crash")
        return original(self, fn, args, timeout)
    monkeypatch.setattr(runner.WorkerProc, "call", call)
    jid, j = run_job(c, {"R/1/a.jpg": enc(synth.layout(311)), "R/1/b.jpg": enc(synth.layout(312))})
    assert j["counts"]["done"] == 2 and j["counts"]["excluded"] == 0 and j["ml"] is False
    assert c.get(f"/api/jobs/{jid}/download.zip").status_code == 200
    c.delete(f"/api/jobs/{jid}", headers=H)
