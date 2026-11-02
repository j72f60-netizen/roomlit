"""Smart organisation of a set of edited photos: duplicates, room types, gallery order.

`organize()` runs in its own short-lived process (it loads an 89 MB model); see app/runner.py.
This package's __init__ is deliberately empty so the web process can import `classes` without loading OpenCV.
"""
from __future__ import annotations

import cv2

from . import arrange
from . import features as F
from .clip import Clip, ClipUnavailable


def organize(sets: list[dict], model_dir: str, threads: int = 1) -> dict:
    """sets: [{"id": sid, "items": [{"id", "preview", "analysis", "pixels"}]}]  ->  {"ml": bool, "sets": {sid: result}}"""
    try:
        clip: Clip | None = Clip(model_dir, threads)
    except ClipUnavailable:
        clip = None
    out: dict = {"ml": clip is not None, "sets": {}}
    for s in sets:
        items = []
        for it in s["items"]:
            img = cv2.imread(it["preview"])
            if img is None:
                continue
            feat = F.extract(img, it["analysis"], it["pixels"])
            ai = arrange.Item(id=it["id"], feat=feat)
            if clip is not None:
                ai.emb = clip.embed(img)
                ai.probs = clip.classify(ai.emb)
                ai.appeal = clip.appeal(ai.emb)
            items.append(ai)
            del img
        r = arrange.arrange(items)
        out["sets"][s["id"]] = {
            "order": r.order, "excluded": r.excluded, "rooms": r.rooms, "similar": r.similar,
            "scores": r.scores, "room_group": r.room_group,
        }
    return out
