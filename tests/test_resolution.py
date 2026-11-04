"""Pro Listing mode (the full professional brief) and "Enhance resolution" (small photos enlarged, same proportions)."""
import io, os
import cv2
import numpy as np
from PIL import Image
from app.engine import imageio, pipeline
from . import synth
from .test_api import H, up, wait, client, authed  # noqa: F401

MAXPX = 80_000_000
pipeline.init_worker(MAXPX, 1)


def run(tmp_path, bgr, mode, enlarge_to=0, name="in.jpg", **save_kw):
    src = str(tmp_path / name)
    synth.save_jpeg(src, bgr, **save_kw)
    dst = str(tmp_path / f"out_{mode}_{enlarge_to}.jpg")
    pipeline.analyze_file(src, str(tmp_path), 1, MAXPX)
    r = pipeline.process_file(src, dst, str(tmp_path), 1, mode, None, MAXPX, ".jpg", None, enlarge_to)
    return src, dst, r


def test_pro_mode_matches_the_brief_on_the_standard_scene(tmp_path):
    bgr = synth.scene()
    outs = {m: cv2.imread(run(tmp_path, bgr, m)[1]) for m in ("natural", "premium", "pro")}
    luma = lambda im: float(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).mean())
    base = luma(bgr)
    assert luma(outs["pro"]) > base + 4                                              # brighter
    assert (cv2.cvtColor(outs["pro"], cv2.COLOR_BGR2GRAY) >= 253).mean() < 0.01      # without blowing highlights
    h0, h1, hp = (synth.hsv(x[synth.SOFA]) for x in (bgr, outs["pro"], outs["premium"]))
    assert np.median(h1[..., 2]) > np.median(hp[..., 2]) > np.median(h0[..., 2])    # blue sofa: brighter than premium does it
    assert abs(float(np.median(h1[..., 0]) - np.median(h0[..., 0]))) < 3.0           # ... in the same blue
    assert 190 < np.median(h1[..., 0]) < 250
    assert np.median(h1[..., 1]) > 0.8 * np.median(h0[..., 1])                       # ... and not washed out


def test_small_photos_are_enlarged_with_the_same_proportions_and_big_ones_are_left_alone(tmp_path):
    small = synth.scene(w=1024, h=768)
    _, dst, r = run(tmp_path, small, "premium", enlarge_to=2048)
    out = Image.open(dst)
    assert out.size == (2048, 1536) and (r["width"], r["height"]) == (2048, 1536)    # 4:3 stays 4:3
    # crisper than a plain enlargement of the same edited photo (interpolation softness is restored, grain is not boosted)
    _, plain, _ = run(tmp_path, small, "premium", enlarge_to=0)
    simple = cv2.resize(cv2.imread(plain), (2048, 1536), interpolation=cv2.INTER_CUBIC)
    lap = lambda im: cv2.Laplacian(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    assert lap(cv2.imread(dst)) > lap(simple)
    assert abs(float(cv2.imread(dst).mean()) - float(simple.mean())) < 3             # same picture, same tones
    tiny = synth.scene(w=480, h=360)                                                 # a thumbnail is never blown up more than 2.5x
    assert Image.open(run(tmp_path, tiny, "premium", enlarge_to=2048, name="tiny.jpg")[1]).size == (1200, 900)
    big = synth.scene(w=2600, h=1700)
    assert Image.open(run(tmp_path, big, "premium", enlarge_to=2048, name="big.jpg")[1]).size == (2600, 1700)


def test_enlarged_photo_keeps_exif_icc_and_gets_matching_size_tags(tmp_path):
    bgr = synth.scene(w=1024, h=683)
    src = str(tmp_path / "e.jpg")
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    ex = Image.Exif(); ex[0x010F] = "TestCam"; sub = ex.get_ifd(0x8769); sub[0xA002] = 1024; sub[0xA003] = 683
    im.save(src, "JPEG", quality=95, exif=ex, icc_profile=synth.srgb_icc())
    pipeline.analyze_file(src, str(tmp_path), 1, MAXPX)
    dst = str(tmp_path / "e_out.jpg")
    pipeline.process_file(src, dst, str(tmp_path), 1, "natural", None, MAXPX, ".jpg", None, 2048)
    out = Image.open(dst)
    assert out.size == (2048, 1366)
    e2 = out.getexif()
    assert e2.get(0x010F) == "TestCam" and out.info.get("icc_profile")
    sub2 = e2.get_ifd(0x8769)
    assert sub2.get(0xA002) == 2048 and sub2.get(0xA003) == out.size[1]


def test_enlarge_option_through_the_api(authed):
    c = authed
    data = cv2.imencode(".jpg", synth.layout(900, 1024, 768), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
    for enlarge, size in ((True, (2048, 1536)), (False, (1024, 768))):
        jid = c.post("/api/jobs", json={"mode": "pro"}, headers=H).json()["id"]
        up(c, jid, "R/1/a.jpg", data)
        wait(c, jid, lambda j: j["counts"]["ready"] == 1)
        c.post(f"/api/jobs/{jid}/start", json={"mode": "pro", "smart": False, "enlarge": enlarge}, headers=H)
        j = wait(c, jid, lambda j: j["counts"]["done"] == 1)
        it = j["items"][0]
        assert j["enlarge"] is enlarge and (it["w"], it["h"]) == size and it["mode"] == "pro"
        got = Image.open(io.BytesIO(c.get(f"/api/jobs/{jid}/items/{it['id']}/download").content))
        assert got.size == size
        c.delete(f"/api/jobs/{jid}", headers=H)
