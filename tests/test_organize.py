"""Duplicate detection, quality choice and gallery ordering (engine level, no web server)."""
import glob, os
import cv2
import numpy as np
import pytest
from app.engine import pipeline
from app.engine.organize.run import organize
from . import synth

MAXPX = 80_000_000
MODELS = os.path.join(os.path.dirname(__file__), "..", "models")
HAVE_MODEL = os.path.exists(os.path.join(MODELS, "vision_model_quantized.onnx"))
SAMPLES = os.path.join(os.path.dirname(__file__), "samples")
need_samples = pytest.mark.skipif(not os.path.isdir(SAMPLES), reason="sample photos not downloaded (tests/fetch_samples.py)")
need_model = pytest.mark.skipif(not (HAVE_MODEL and os.path.isdir(SAMPLES)), reason="room model / samples missing")
pipeline.init_worker(MAXPX, 1)


def run(tmp_path, named: dict, model=True):
    """named: {name: bgr image or path}.  Returns (result for the single set, {id: name})."""
    items, names = [], {}
    for i, (n, src) in enumerate(named.items(), 1):
        if isinstance(src, str):
            path = src
        else:
            path = str(tmp_path / f"in_{i}.jpg"); synth.save_jpeg(path, src, quality=95)
        r = pipeline.analyze_file(path, str(tmp_path), i, MAXPX)
        items.append({"id": i, "preview": str(tmp_path / f"{i}_before.jpg"), "analysis": r["analysis"], "pixels": r["width"] * r["height"]})
        names[i] = n
    res = organize([{"id": 0, "items": items}], MODELS if model else str(tmp_path / "nomodel"))
    return res["sets"][0], names


def excluded_names(r, names): return {names[i]: names[e["dup_of"]] for i, e in r["excluded"].items()}


def test_identical_images_with_different_names_are_one_photo(tmp_path):
    a = synth.layout(1)
    r, n = run(tmp_path, {"IMG_0001.jpg": a, "copy of living.jpg": a.copy(), "other.jpg": synth.layout(2)}, model=False)
    assert len(r["excluded"]) == 1 and len(r["order"]) == 2
    assert set(excluded_names(r, n).values()) <= {"IMG_0001.jpg", "copy of living.jpg"}
    assert "other.jpg" in [n[i] for i in r["order"]]


def test_same_angle_with_different_lighting_size_and_noise_is_detected(tmp_path):
    a = synth.layout(3)
    r, n = run(tmp_path, {
        "orig.jpg": a, "darker_warm.jpg": synth.relit(a, 1.7, 0.7, (1.12, 1.0, 0.88)), "brighter.jpg": synth.relit(a, 0.55, 1.05, (0.95, 1.0, 1.05)),
        "small_q60.jpg": synth.resized_q(a, 0.5, 60),
        "noisy_dim.jpg": np.clip(a.astype(np.float32) * 0.5 + np.random.default_rng(1).normal(0, 9, a.shape), 0, 255).astype(np.uint8),
        "handheld_shift.jpg": synth.shifted(a, 640 * 0.012, 480 * 0.008),
        "different_room.jpg": synth.layout(4)}, model=False)
    assert len(r["order"]) == 2, excluded_names(r, n)                      # one shot + the other room
    assert "different_room.jpg" in [n[i] for i in r["order"]]


def test_sharper_and_larger_version_is_the_one_kept(tmp_path):
    a = synth.layout(5, w=1000, h=750)
    blurred = cv2.GaussianBlur(a, (0, 0), 3.0)
    r, n = run(tmp_path, {"blurry.jpg": blurred, "sharp.jpg": a, "small.jpg": synth.resized_q(a, 0.4, 90)}, model=False)
    assert [n[i] for i in r["order"]] == ["sharp.jpg"]
    assert set(excluded_names(r, n)) == {"blurry.jpg", "small.jpg"}


def test_different_viewpoint_of_the_same_scene_is_kept(tmp_path):
    a = synth.layout(6)
    r, n = run(tmp_path, {"front.jpg": a, "from_the_side.jpg": synth.other_angle(a)}, model=False)
    assert len(r["order"]) == 2 and not r["excluded"]


def test_single_photos_and_empty_sets_do_not_break(tmp_path):
    r, n = run(tmp_path, {"only.jpg": synth.layout(7)}, model=False)
    assert r["order"] == [1] and not r["excluded"]


def test_organizer_works_without_the_room_model(tmp_path):
    r, n = run(tmp_path, {"a.jpg": synth.layout(8), "b.jpg": synth.layout(9)}, model=False)
    assert len(r["order"]) == 2 and all(v["label"] == "other" and not v["sure"] for v in r["rooms"].values())


def test_deterministic(tmp_path):
    a = synth.layout(10)
    imgs = {"a.jpg": a, "b.jpg": synth.relit(a), "c.jpg": synth.layout(11), "d.jpg": synth.layout(12)}
    r1, _ = run(tmp_path, imgs, model=False); r2, _ = run(tmp_path, imgs, model=False)
    assert r1["order"] == r2["order"] and r1["excluded"] == r2["excluded"]


# ---------------------------------------------------------------- real photos
@need_samples
def test_real_photos_of_one_room_from_different_angles_are_all_kept(tmp_path):
    for group in ("Hotel Room A/Bedroom", "Hotel Room B"):
        files = sorted(glob.glob(os.path.join(SAMPLES, group, "*.jpg")))
        r, n = run(tmp_path, {os.path.basename(f): f for f in files}, model=HAVE_MODEL)
        assert not r["excluded"], excluded_names(r, n)
        assert len(r["order"]) == len(files)


@need_samples
def test_real_photo_relit_and_resized_is_removed_but_other_angles_stay(tmp_path):
    files = sorted(glob.glob(os.path.join(SAMPLES, "Hotel Room A/Bedroom/*.jpg")))
    base = cv2.imread(files[1])
    named = {os.path.basename(f): f for f in files}
    named["bed_2_relit_small.jpg"] = synth.resized_q(synth.relit(base, 1.4, 0.75, (1.08, 1.0, 0.92)), 0.4, 70)
    named["bed_2_copy.jpg"] = base.copy()
    r, n = run(tmp_path, named, model=HAVE_MODEL)
    ex = excluded_names(r, n)
    assert len(ex) == 2, ex                                            # the two copies of bed_2 are removed ...
    assert len(r["order"]) == len(files)                               # ... every real angle is still there
    assert {"bed_1.jpg", "bed_3.jpg", "bed_4.jpg", "bed_5.jpg", "bed_6.jpg"} <= {n[i] for i in r["order"]}


@need_model
def test_gallery_order_follows_the_airbnb_sequence(tmp_path):
    pick = {
        "living": "Apartments/Modern/modern_living.jpg", "living2": "Apartments/Rio/living_big.jpg",
        "bed": "Hotel Room B/room_2.jpg", "bed2": "Apartments/Tianhe/tianhe_bed.jpg",
        "kitchen": "Classes/kitchen/k3.jpg", "bath": "Classes/bathroom/b1.jpg", "bath2": "Classes/bathroom/b4.jpg",
        "dining": "Classes/dining/d2.jpg", "view": "Classes/view/v2.jpg", "exterior": "Classes/exterior/e1.jpg", "parking": "Classes/parking/p2.jpg"}
    r, n = run(tmp_path, {k: os.path.join(SAMPLES, v) for k, v in pick.items()})
    assert not r["excluded"]
    order = [n[i] for i in r["order"]]
    cat = {"living": 2, "living2": 2, "bed": 3, "bed2": 3, "kitchen": 4, "bath": 5, "bath2": 5, "dining": 6, "view": 7, "exterior": 7, "parking": 7}
    assert order[0] in ("living", "living2", "bed", "bed2")                    # the cover is a main space, not a bathroom
    tail = [cat[k] for k in order[1:]]
    assert tail == sorted(tail), order                                        # living -> bedrooms -> kitchen -> baths -> dining -> views
    assert order.index("parking") > order.index("view")
    rooms = {n[i]: v["label"] for i, v in r["rooms"].items()}
    assert rooms["kitchen"] == "kitchen" and rooms["bath"] == "bathroom" and rooms["bed"] == "bedroom" and rooms["exterior"] == "exterior"


@need_model
def test_uncertain_room_labels_are_flagged_not_forced(tmp_path):
    r, n = run(tmp_path, {"l1": os.path.join(SAMPLES, "Classes/living/l1.jpg"), "p1": os.path.join(SAMPLES, "Classes/parking/p1.jpg"),
                          "k": os.path.join(SAMPLES, "Classes/kitchen/k3.jpg")})
    byname = {n[i]: v for i, v in r["rooms"].items()}
    assert byname["k"]["sure"] is True and byname["k"]["label"] == "kitchen"
    assert not byname["l1"]["sure"] and not byname["p1"]["sure"]                # weak guesses are offered as suggestions
    assert all(len(v["alts"]) == 3 for v in byname.values())


def ring(a, radius, k):
    """The same room from slightly different spots: k camera positions on a circle (% of the width) around `a`."""
    out = []
    for n in range(k):
        ang = 2 * np.pi * n / k
        out.append(synth.shifted(a, radius * a.shape[1] * np.cos(ang), radius * a.shape[0] * np.sin(ang)))
    return out


def test_one_angle_shot_many_times_keeps_only_the_best_two(tmp_path):
    a = synth.layout(8, w=960, h=720)
    sharp = {f"take_{n}.jpg": im for n, im in enumerate(ring(a, 0.07, 3), 1)}
    # the original (sharpest) plus three nudged takes with a little more blur each: six photos of one angle
    named = {"best.jpg": a, **{k: cv2.GaussianBlur(v, (0, 0), 0.6 + 0.4 * n) for n, (k, v) in enumerate(sharp.items())},
             "other_room.jpg": synth.layout(9, w=960, h=720)}
    r, n = run(tmp_path, named, model=False)
    kept = [n[i] for i in r["order"]]
    assert "other_room.jpg" in kept and "best.jpg" in kept
    from_angle = [k for k in kept if k != "other_room.jpg"]
    assert len(from_angle) == 2, (kept, excluded_names(r, n))                 # best two of that angle, not all four
    angle_ex = {n[i]: e for i, e in r["excluded"].items() if e.get("kind") == "angle"}
    assert len(angle_ex) == 2 and all(n[e["dup_of"]] == "best.jpg" for e in angle_ex.values())


def test_different_angles_are_never_capped(tmp_path):
    a = synth.layout(10, w=960, h=720)
    r, n = run(tmp_path, {"front.jpg": a, "side.jpg": synth.other_angle(a), "far_corner.jpg": synth.layout(11, w=960, h=720),
                          "bed.jpg": synth.layout(12, w=960, h=720)}, model=False)
    assert len(r["order"]) == 4 and not r["excluded"]
