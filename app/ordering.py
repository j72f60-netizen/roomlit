"""Gallery ordering from stored per-photo facts (pure Python: runs in the web process, no OpenCV / NumPy).

Used when the user changes room labels and asks for the suggested order again.  The first ordering of a set
(which also uses image embeddings to spread out similar angles) is computed by the organizer process.
"""
from __future__ import annotations

from .engine.organize.classes import CATEGORY, HERO_PRIOR, SUBORDER


def pick_hero(items: list[dict]) -> int:
    def v(it):
        prior = HERO_PRIOR.get(it["label"], 0.2) * (1.0 if it["sure"] else 0.6)
        return 0.5 * it["score"] + 0.25 * it["appeal"] + 0.25 * prior
    return max(items, key=lambda it: (v(it), -it["id"]))["id"]


def simple_order(items: list[dict]) -> list[int]:
    """items: [{id, label, sure, score, appeal, group}] -> ids: hero first, then living, bedrooms, kitchen, bathrooms,
    dining/amenities, views/entrances/parking; photos of one physical room stay together, best first."""
    if not items:
        return []
    hero = pick_hero(items)
    out = [hero]
    rest = [it for it in items if it["id"] != hero]
    buckets: dict[tuple[int, int], list[dict]] = {}
    for it in rest:
        buckets.setdefault((CATEGORY.get(it["label"], 6), SUBORDER.get(it["label"], 4)), []).append(it)
    for k in sorted(buckets):
        groups: dict[int, list[dict]] = {}
        for it in buckets[k]:
            groups.setdefault(it["group"], []).append(it)
        for g in sorted(groups.values(), key=lambda m: -max(x["score"] for x in m)):
            out.extend(x["id"] for x in sorted(g, key=lambda x: (-x["score"], x["id"])))
    return out
