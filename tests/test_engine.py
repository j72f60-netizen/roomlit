import os, io
import numpy as np, cv2
import pytest
from PIL import Image
from app.engine import pipeline, imageio
from . import synth  # noqa

MAXPX = 80_000_000
pipeline.init_worker(MAXPX, 1)


def run(tmp_path, bgr, mode, name="in.jpg", **save_kw):
    src = str(tmp_path / name)
    synth.save_jpeg(src, bgr, **save_kw)
    dst = str(tmp_path / f"out_{mode}.jpg")
    pv = str(tmp_path); os.makedirs(pv, exist_ok=True)
    pipeline.analyze_file(src, pv, 1, MAXPX)
    r = pipeline.process_file(src, dst, pv, 1, mode, None, MAXPX)
    return src, dst, r


def test_dimensions_exif_icc_preserved(tmp_path):
    bgr = synth.scene(w=640, h=480)
    src, dst, r = run(tmp_path, bgr, "premium", orientation=6, icc=True)
    a, b = Image.open(src), Image.open(dst)
    assert a.size == b.size == (640, 480)                       # never crops or rescales
    assert b.getexif().get(0x0112) == 6                          # orientation tag carried over, pixels untouched
    assert b.getexif().get(0x010F) == "TestCam"
    assert b.info.get("icc_profile") == a.info.get("icc_profile") and b.info.get("icc_profile")
    prev = Image.open(tmp_path / "1_after.jpg")                  # previews are shown upright
    assert prev.size == (480, 640)


@pytest.mark.parametrize("mode", ["natural", "premium", "bright"])
def test_blue_sofa_brighter_same_hue(tmp_path, mode):
    bgr = synth.scene()
    _, dst, _ = run(tmp_path, bgr, mode)
    out = cv2.imread(dst)
    h0, h1 = synth.hsv(bgr[synth.SOFA]), synth.hsv(out[synth.SOFA])
    dh = abs(float(np.median(h1[..., 0]) - np.median(h0[..., 0])))
    assert dh < 3.0, f"sofa hue moved {dh:.1f} degrees"
    assert 190 < np.median(h1[..., 0]) < 250                    # still blue
    assert np.median(h1[..., 2]) > np.median(h0[..., 2])        # brighter


def test_modes_are_ordered_and_visibly_different(tmp_path):
    bgr = synth.scene()
    means = {}
    for m in ("natural", "premium", "bright"):
        _, dst, _ = run(tmp_path, bgr, m)
        means[m] = float(cv2.cvtColor(cv2.imread(dst), cv2.COLOR_BGR2GRAY).mean())
    base = float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean())
    assert base < means["natural"] < means["premium"] < means["bright"]
    assert means["premium"] - means["natural"] > 4 and means["bright"] - means["premium"] > 4


def test_whites_get_cleaner_not_colourful(tmp_path):
    bgr = synth.scene()
    _, dst, _ = run(tmp_path, bgr, "bright")
    out = cv2.imread(dst)
    s0, s1 = np.median(synth.hsv(bgr[synth.BED])[..., 1]), np.median(synth.hsv(out[synth.BED])[..., 1])
    assert s1 <= s0 + 1e-3
    assert np.median(synth.hsv(out[synth.BED])[..., 2]) > np.median(synth.hsv(bgr[synth.BED])[..., 2])


def test_windows_not_more_blown_out_and_defects_kept(tmp_path):
    bgr = synth.scene()
    bgr[200:230, 100:104] = 255                                   # a "defect": thin bright scratch on the wall
    _, dst, _ = run(tmp_path, bgr, "bright")
    out = cv2.imread(dst)
    assert (out[synth.WINDOW] >= 252).mean() <= (bgr[synth.WINDOW] >= 252).mean() + 1e-6
    scratch_in = bgr[200:230, 98:106].astype(float).mean(); scratch_out = out[200:230, 98:106].astype(float).mean()
    assert scratch_out > np.median(out[200:230, 130:160]) + 10    # the defect is still there


def test_deterministic_output(tmp_path):
    bgr = synth.scene()
    _, d1, _ = run(tmp_path, bgr, "premium")
    b1 = open(d1, "rb").read()
    _, d2, _ = run(tmp_path, bgr, "premium")
    assert b1 == open(d2, "rb").read()


def test_structure_unchanged(tmp_path):
    """Edited luma must be a smooth monotone-ish function of the original: no objects added or removed."""
    from skimage.metrics import structural_similarity as ssim
    bgr = synth.scene(noise=1.0)
    _, dst, _ = run(tmp_path, bgr, "premium")
    a = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY); b = cv2.cvtColor(cv2.imread(dst), cv2.COLOR_BGR2GRAY)
    A = np.stack([a.ravel(), np.ones(a.size)], 1).astype(np.float32)
    fit = np.clip((A @ np.linalg.lstsq(A, b.ravel().astype(np.float32), rcond=None)[0]).reshape(a.shape), 0, 255).astype(np.uint8)
    assert ssim(fit, b, data_range=255) > 0.93


def test_strip_processing_matches_whole_image(tmp_path):
    """Strips must not leave seams: tiny strips and big strips give (almost) identical pixels."""
    from app.engine import enhance
    bgr = synth.scene(w=900, h=700)
    src = str(tmp_path / "s.jpg"); synth.save_jpeg(src, bgr)
    meta = imageio.inspect(src, MAXPX)
    outs = []
    for strip in (50_000, 10_000_000):
        enhance.STRIP_PIXELS = strip
        img = imageio.load_bgr(src, meta); an = enhance.analyze_bgr(img)
        enhance.enhance_inplace(img, enhance.make_context(img, an, enhance.get_preset("premium") if hasattr(enhance, "get_preset") else __import__("app.engine.presets", fromlist=["x"]).get_preset("premium")))
        outs.append(img)
    enhance.STRIP_PIXELS = 400_000
    diff = np.abs(outs[0].astype(int) - outs[1].astype(int))
    assert diff.mean() < 0.05 and np.percentile(diff, 99.9) <= 3


def test_png_stays_png_and_heic_becomes_jpg(tmp_path):
    bgr = synth.scene(w=400, h=300)
    png = str(tmp_path / "a.png"); cv2.imwrite(png, bgr)
    out = str(tmp_path / "a_out.png")
    r = pipeline.process_file(png, out, str(tmp_path), 2, "natural", None, MAXPX)
    assert Image.open(out).format == "PNG" and Image.open(out).size == (400, 300)
    if imageio.HEIC_OK:
        import pillow_heif
        heic = str(tmp_path / "a.heic")
        pillow_heif.from_pillow(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))).save(heic)
        res = pipeline.analyze_file(heic, str(tmp_path), 3, MAXPX)
        assert res["out_ext"] == ".jpg" and (res["width"], res["height"]) == (400, 300)


def test_grayscale_and_cmyk_inputs(tmp_path):
    g = tmp_path / "g.jpg"; Image.fromarray(np.tile(np.linspace(30, 220, 300, dtype=np.uint8), (200, 1))).save(g)
    c = tmp_path / "c.jpg"; Image.fromarray(cv2.cvtColor(synth.scene(w=300, h=200), cv2.COLOR_BGR2RGB)).convert("CMYK").save(c)
    for p in (g, c):
        out = str(tmp_path / ("o_" + p.name))
        pipeline.process_file(str(p), out, str(tmp_path), 4, "premium", None, MAXPX)
        assert Image.open(out).size == Image.open(p).size


def test_bad_and_oversized_files_are_rejected_clearly(tmp_path):
    bad = tmp_path / "bad.jpg"; bad.write_bytes(b"not an image at all")
    with pytest.raises(imageio.ImageError):
        pipeline.analyze_file(str(bad), str(tmp_path), 5, MAXPX)
    big = tmp_path / "big.png"; Image.new("RGB", (4000, 3000)).save(big)
    with pytest.raises(imageio.ImageError) as e:
        pipeline.analyze_file(str(big), str(tmp_path), 6, 10_000_000)
    assert "not downscaled" in str(e.value)
