"""What the user gets by default: duplicates removed, photos arranged and numbered, and the folder / ZIP called
`<the folder that was sent> بعد التعديل` (apartment code + number as written, then "after editing")."""
import io, urllib.parse, zipfile
import pytest
from . import synth
from .test_api import H, up, wait, client, authed  # noqa: F401
from .test_organize_api import build_files, enc

AFTER = "بعد التعديل"


def disposition_name(r) -> str:
    cd = r.headers["content-disposition"]
    return urllib.parse.unquote(cd.split("filename*=utf-8''")[1]) if "filename*=" in cd else cd.split('filename="')[1].rstrip('"')


@pytest.fixture
def default_job(authed):
    """Upload and start with exactly what the page sends by default (no options in the start request)."""
    c = authed
    files = build_files()
    jid = c.post("/api/jobs", json={"mode": "premium"}, headers=H).json()["id"]
    for p, d in files.items():
        assert up(c, jid, p, d).status_code == 200
    wait(c, jid, lambda j: j["counts"]["ready"] == len(files))
    assert c.post(f"/api/jobs/{jid}/start", json={"mode": "premium"}, headers=H).status_code == 200
    j = wait(c, jid, lambda j: j["phase"] in ("done", "failed") and j["counts"]["queued"] + j["counts"]["processing"] == 0)
    yield c, jid, j
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_default_run_removes_duplicates_and_arranges(default_job):
    c, jid, j = default_job
    cnt = j["counts"]
    assert j["smart"] is True and (cnt["total"], cnt["excluded"], cnt["final"], cnt["done"]) == (9, 3, 6, 6)
    assert all(s["organized"] for s in j["sets"]) and all(i["pos"] == 0 for i in j["items"] if i["ex"])


def test_default_zip_is_named_after_the_folder_plus_after_editing_and_numbered(default_job):
    c, jid, j = default_job
    r = c.get(f"/api/jobs/{jid}/download.zip")                                    # no options: what the button gives
    assert r.status_code == 200 and disposition_name(r) == f"Al Khuzama {AFTER}.zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert len(names) == 6                                                        # the 3 duplicates are not in the delivery
    assert all(n.startswith(f"Al Khuzama {AFTER}/") for n in names)               # root folder: as written + after editing
    assert {n.split("/")[1] for n in names} == {"1", "02"}                        # sub-folders (apartment numbers) as uploaded
    one = sorted(n for n in names if n.split("/")[1] == "1")
    assert [n.split("/")[2][:5] for n in one] == ["01 - ", "02 - ", "03 - ", "04 - "]      # arranged order carried by the numbers
    assert not any(w in n for n in names for w in ("Edited", "Airbnb"))


def test_suffix_can_be_changed_removed_and_is_always_safe(default_job):
    c, jid, j = default_job
    q = lambda **kw: c.get(f"/api/jobs/{jid}/download.zip", params=kw)
    r = q(suffix="Edited")
    assert disposition_name(r) == "Al Khuzama Edited.zip"
    assert {n.split("/")[0] for n in zipfile.ZipFile(io.BytesIO(r.content)).namelist()} == {"Al Khuzama Edited"}
    r = q(suffix="")                                                              # nothing added: the folder name exactly as sent
    assert disposition_name(r) == "Al Khuzama.zip"
    assert {n.split("/")[0] for n in zipfile.ZipFile(io.BytesIO(r.content)).namelist()} == {"Al Khuzama"}
    r = q(suffix="../evil/x:y*?")                                                 # nothing here can climb out of the folder
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert len({n.split("/")[0] for n in names}) == 1 and ".." not in "".join(names) and "\\" not in "".join(names)
    assert all(n.split("/")[0].startswith("Al Khuzama ") for n in names)


def test_log_shows_original_and_final_path(default_job):
    c, jid, j = default_job
    log = c.get(f"/api/jobs/{jid}/log.csv").content.decode("utf-8-sig")
    assert "final_path" in log and f"Al Khuzama {AFTER}/1/01 - " in log and "IMG_001.jpg" in log and "excluded" in log


def test_two_root_folders_each_get_the_suffix_and_the_zip_is_generic(authed):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    for p, k in (("Villa 1/a.jpg", 1), ("Villa 2/b.jpg", 2)):
        up(c, jid, p, enc(synth.layout(600 + k)))
    wait(c, jid, lambda j: j["counts"]["ready"] == 2)
    c.post(f"/api/jobs/{jid}/start", json={}, headers=H)
    wait(c, jid, lambda j: j["counts"]["done"] == 2)
    r = c.get(f"/api/jobs/{jid}/download.zip?numbering=0")
    assert disposition_name(r) == "Roomlit export.zip"
    assert sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == [f"Villa 1 {AFTER}/a.jpg", f"Villa 2 {AFTER}/b.jpg"]
    c.delete(f"/api/jobs/{jid}", headers=H)
