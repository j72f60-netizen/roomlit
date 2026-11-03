"""Retouch (remove a small object / smooth fabric): engine behaviour and the API around it."""
import io
import cv2
import numpy as np
import pytest
from PIL import Image
from app.engine import imageio, retouch
from app.engine.retouch_ops import BadStrokes, clean_ops, display_to_stored
from . import synth
from .test_api import H, up, wait, client, authed  # noqa: F401


def wall(w=900, h=600, seed=5):
    """A softly lit wall with a little grain: the kind of background a broom handle leans on."""
    rng = np.random.default_rng(seed)
    gx = np.linspace(185, 150, w, dtype=np.float32)[None, :, None]
    gy = np.linspace(-8, 14, h, dtype=np.float32)[:, None, None]
    img = np.clip(gx + gy + rng.normal(0, 2.2, (h, w, 1)) + np.array([0, 4, 9], np.float32)[None, None, :], 0, 255)
    return img.astype(np.uint8)


def stroke(pts, r, kind="remove"):
    return {"t": kind, "r": r, "pts": pts}


# ---------------------------------------------------------------- coordinates
@pytest.mark.parametrize("orientation", range(1, 9))
def test_display_coordinates_map_back_to_the_stored_layout(orientation):
    h, w = 60, 100
    stored = np.zeros((h, w, 3), np.uint8)
    cv2.circle(stored, (70, 15), 4, (255, 255, 255), -1)                           # marker at (0.70, 0.25) of the stored pixels
    shown = imageio._apply_orientation(stored, orientation)                        # what the user sees and paints on
    ys, xs = np.nonzero(shown[:, :, 0])
    u, v = xs.mean() / shown.shape[1], ys.mean() / shown.shape[0]
    sx, sy = display_to_stored(u, v, orientation)
    assert abs(sx - 70 / w) < 0.03 and abs(sy - 15 / h) < 0.05, (orientation, sx, sy)


def test_stroke_validation_rejects_anything_odd():
    ok = [{"t": "remove", "r": 0.01, "pts": [[0.1, 0.2], [0.3, 0.4]]}]
    assert clean_ops(ok) == [{"t": "remove", "r": 0.01, "pts": [[0.1, 0.2], [0.3, 0.4]]}]
    assert clean_ops([]) == []
    bad = [None, "x", [{"t": "paint", "r": 0.01, "pts": [[0, 0]]}], [{"t": "remove", "r": 0.5, "pts": [[0, 0]]}],
           [{"t": "remove", "r": 0.01, "pts": []}], [{"t": "remove", "r": 0.01, "pts": [[0, 0, 0]]}],
           [{"t": "remove", "r": 0.01, "pts": [["a", 0]]}], [{"t": "remove", "r": 0.01, "pts": [[3.0, 0.2]]}],
           [{"t": "remove", "r": True, "pts": [[0, 0]]}], ok * 61, [{"t": "smooth", "r": 0.01, "pts": [[0.1, 0.1]] * 601}]]
    for b in bad:
        with pytest.raises(BadStrokes):
            clean_ops(b)


# ---------------------------------------------------------------- remove
def test_a_thin_object_on_a_plain_wall_disappears_and_nothing_else_moves():
    clean = wall()
    img = clean.copy()
    cv2.line(img, (300, 40), (340, 560), (40, 80, 140), 13, cv2.LINE_AA)           # a broom handle leaning on the wall
    before = img.copy()
    on_stick = cv2.dilate((np.abs(img.astype(int) - clean.astype(int)).max(2) > 10).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    n = retouch.apply(img, [stroke([[300 / 900, 40 / 600], [340 / 900, 560 / 600]], 0.0075)])
    assert n == 1 and img.shape == clean.shape
    assert np.abs(before.astype(int) - clean.astype(int))[on_stick].mean() > 40
    assert np.abs(img.astype(int) - clean.astype(int))[on_stick].mean() < 8          # the handle is gone (looks like the wall)
    far = cv2.dilate(on_stick.astype(np.uint8), np.ones((61, 61), np.uint8)) == 0
    assert np.array_equal(img[far], before[far])                                      # pixels away from the stroke are untouched


def test_remove_is_deterministic_and_leaves_an_empty_stroke_list_alone():
    a = wall(); cv2.circle(a, (400, 300), 12, (20, 20, 200), -1)
    b = a.copy(); c = a.copy(); orig = a.copy()
    op = [stroke([[400 / 900, 300 / 600]], 0.012)]
    retouch.apply(b, op); retouch.apply(c, op)
    assert np.array_equal(b, c) and not np.array_equal(b, orig)
    assert retouch.apply(a, []) == 0 and np.array_equal(a, orig)


def test_strokes_follow_the_displayed_orientation():
    stored = wall(w=800, h=500)
    cv2.rectangle(stored, (560, 100), (580, 400), (30, 60, 150), -1)                  # a pole, in the stored (unrotated) pixels
    orig = stored.copy()
    # orientation 6: the photo is shown rotated 90 degrees clockwise, so the pole is horizontal on screen
    shown = imageio._apply_orientation(stored, 6)
    ys, xs = np.nonzero((np.abs(shown.astype(int) - imageio._apply_orientation(wall(w=800, h=500), 6).astype(int)).max(2) > 40))
    y_mid = ys.mean() / shown.shape[0]
    op = stroke([[xs.min() / shown.shape[1], y_mid], [xs.max() / shown.shape[1], y_mid]], 0.012)
    retouch.apply(stored, [op], orientation=6)
    pole = (slice(100, 401), slice(560, 581))
    assert np.abs(stored[pole].astype(int) - wall(w=800, h=500)[pole].astype(int)).mean() < 10
    assert not np.array_equal(stored, orig)


def test_big_strokes_cross_tile_borders_without_a_seam(monkeypatch):
    img = wall(w=2000, h=1500)
    cv2.line(img, (600, 100), (1500, 1400), (50, 90, 160), 30, cv2.LINE_AA)
    op = [stroke([[600 / 2000, 100 / 1500], [1500 / 2000, 1400 / 1500]], 0.0125)]
    a = img.copy(); retouch.apply(a, op)
    monkeypatch.setattr(retouch, "TILE", 100_000)                                     # one single tile
    b = img.copy(); retouch.apply(b, op)
    assert np.abs(a.astype(int) - b.astype(int)).mean() < 0.6


# ---------------------------------------------------------------- smooth fabric
def sheet(w=900, h=600, seed=9):
    rng = np.random.default_rng(seed)
    y = np.linspace(225, 200, w, dtype=np.float32)[None, :].repeat(h, 0)
    n = rng.normal(0, 1, (h // 4, w // 4)).astype(np.float32)
    creases = cv2.resize(cv2.GaussianBlur(n, (0, 0), 3, sigmaY=1.0), (w, h), interpolation=cv2.INTER_CUBIC)
    creases = 9 * creases / creases.std()                                             # +-9 levels of soft, streaky creases
    img = np.stack([y + creases + rng.normal(0, 1.5, (h, w)) + d for d in (-6, 0, 4)], 2)
    img[:, :, :] = np.clip(img, 0, 255)
    return img.astype(np.uint8), creases


def crease_energy(img, mask):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(cv2.GaussianBlur(g, (0, 0), 2) - cv2.GaussianBlur(g, (0, 0), 30))[mask].mean())


def test_smoothing_softens_creases_keeps_colour_and_edges():
    img, _ = sheet()
    cv2.rectangle(img, (0, 0), (900, 40), (40, 70, 110), -1)                          # a dark band: a strong edge next to the sheet
    before = img.copy()
    op = [stroke([[0.1 + 0.1 * k, 0.55] for k in range(9)], 0.06, "smooth")]
    painted = np.zeros((600, 900), np.uint8)
    m, x0, y0 = retouch._stroke_mask(op[0], 900, 600, 1); painted[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
    inside = cv2.erode(painted, np.ones((25, 25), np.uint8)) > 0
    retouch.apply(img, op)
    assert crease_energy(img, inside) < 0.7 * crease_energy(before, inside)           # creases clearly softer
    ycc0, ycc1 = cv2.cvtColor(before, cv2.COLOR_BGR2YCrCb), cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    assert np.abs(ycc0[:, :, 1:].astype(int) - ycc1[:, :, 1:].astype(int)).max() <= 1  # colour untouched (no tints)
    assert np.abs(img.astype(int) - before.astype(int)).max() <= 40                   # a touch-up, never a repaint
    far = cv2.dilate(painted, np.ones((151, 151), np.uint8)) == 0
    assert np.array_equal(img[far], before[far])
    band = (slice(30, 50), slice(0, 900))                                             # the dark band's edge keeps its contrast
    assert abs(float(img[band].mean()) - float(before[band].mean())) < 3


# ---------------------------------------------------------------- API
def png_jpeg(img):
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()


def test_retouch_through_the_api_edits_again_keeps_names_and_survives_re_edit(authed):
    c = authed
    clean = wall(w=900, h=600)
    img = clean.copy(); cv2.line(img, (300, 40), (340, 560), (40, 80, 140), 13, cv2.LINE_AA)
    jid = c.post("/api/jobs", json={"mode": "natural"}, headers=H).json()["id"]
    assert up(c, jid, "Villa/1/pole.jpg", png_jpeg(img)).status_code == 200
    wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    c.post(f"/api/jobs/{jid}/start", json={"smart": False}, headers=H)
    j = wait(c, jid, lambda j: j["counts"]["done"] == 1)
    it = j["items"][0]
    assert it["rt"] == 0
    first = c.get(f"/api/jobs/{jid}/items/{it['id']}/download").content

    ops = [stroke([[300 / 900, 40 / 600], [340 / 900, 560 / 600]], 0.0075)]
    r = c.post(f"/api/jobs/{jid}/items/{it['id']}/retouch", json={"ops": ops}, headers=H)
    assert r.status_code == 200 and r.json() == {"ok": True, "queued": True}
    j = wait(c, jid, lambda j: j["items"][0]["v"] == it["v"] + 1 and j["counts"]["done"] == 1)
    assert j["items"][0]["rt"] == 1 and j["items"][0]["name"] == "pole.jpg" and j["items"][0]["out"] == "Villa/1/pole.jpg"
    second = c.get(f"/api/jobs/{jid}/items/{it['id']}/download").content
    a, b = (np.asarray(Image.open(io.BytesIO(x)).convert("RGB")).astype(int) for x in (first, second))
    assert a.shape == b.shape == (600, 900, 3)
    stick = (slice(100, 500), slice(305, 345))
    assert np.abs(a[stick] - b[stick]).mean() > 10                                    # the handle is gone from the output
    assert c.get(f"/api/jobs/{jid}/items/{it['id']}/retouch").json()["ops"] == clean_ops(ops)   # stored with 5 decimals

    # a later "re-edit all" must keep the touch-up
    c.post(f"/api/jobs/{jid}/reprocess", json={"mode": "bright"}, headers=H)
    j = wait(c, jid, lambda j: j["items"][0]["v"] == it["v"] + 2 and j["counts"]["done"] == 1)
    third = np.asarray(Image.open(io.BytesIO(c.get(f"/api/jobs/{jid}/items/{it['id']}/download").content)).convert("RGB")).astype(int)
    assert j["items"][0]["rt"] == 1 and np.abs(third[stick] - a[stick]).mean() > 10

    # clearing the strokes brings the handle back
    assert c.post(f"/api/jobs/{jid}/items/{it['id']}/retouch", json={"ops": []}, headers=H).status_code == 200
    j = wait(c, jid, lambda j: j["items"][0]["v"] == it["v"] + 3 and j["counts"]["done"] == 1)
    assert j["items"][0]["rt"] == 0
    c.delete(f"/api/jobs/{jid}", headers=H)


def test_retouch_api_rejects_bad_input_and_needs_a_login(authed, client):
    c = authed
    jid = c.post("/api/jobs", json={}, headers=H).json()["id"]
    up(c, jid, "R/1/a.jpg", png_jpeg(wall(w=300, h=200)))
    j = wait(c, jid, lambda j: j["counts"]["ready"] == 1)
    iid = j["items"][0]["id"]
    for body in ({}, {"ops": "x"}, {"ops": [{"t": "remove", "r": 9, "pts": [[0, 0]]}]}, {"ops": [{"t": "zap", "r": 0.01, "pts": [[0, 0]]}]}):
        r = c.post(f"/api/jobs/{jid}/items/{iid}/retouch", json=body, headers=H)
        assert r.status_code == 400 and r.json()["error"] == "bad_strokes"
    ok = {"ops": [stroke([[0.5, 0.5]], 0.02)]}
    r = c.post(f"/api/jobs/{jid}/items/{iid}/retouch", json=ok, headers=H)           # not edited yet: strokes are kept for later
    assert r.status_code == 200 and r.json()["queued"] is False
    assert c.get(f"/api/jobs/{jid}/items/999/retouch").status_code == 404
    c.delete(f"/api/jobs/{jid}", headers=H)
    from fastapi.testclient import TestClient
    import app.main as main
    stranger = TestClient(main.app)                                                   # no session cookie
    assert stranger.post(f"/api/jobs/{jid}/items/{iid}/retouch", json=ok, headers=H).status_code == 401
    assert stranger.get(f"/api/jobs/{jid}/items/{iid}/retouch").status_code == 401
