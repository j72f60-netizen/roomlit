"""Duplicate removal and gallery ordering for ONE apartment (one folder of photos).

Principles
* A photo is dropped only when it is the same shot as a better photo (same viewpoint, geometrically verified).
  Different angles of the same room, or the same furniture, are never duplicates.
* Anything uncertain is kept: borderline pairs are flagged "similar" and left in.
* Room labels carry a confidence; weak ones are marked unsure so the UI can offer them as editable suggestions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import features as F
from .classes import CATEGORY, HERO_PRIOR, SUBORDER

# --- decision thresholds (see tests/explore_pairs.py for the measurements behind them)
DUP_MIN_INLIERS = 100
DUP_MIN_RATIO = 0.85
DUP_MAX_D_MEAN = 0.04
DUP_MAX_D_MAX = 0.08
DUP_NCC = 0.985                       # textureless identical frames
SIM_MIN_INLIERS = 40
SIM_MIN_RATIO = 0.35
SIM_MAX_D_MEAN = 0.08
ROOM_MIN_INLIERS = 20
ROOM_MIN_RATIO = 0.30
SURE_P = 0.55                         # room label is "sure" above this probability ...
SURE_MARGIN = 0.20                    # ... and this lead over the runner-up
MAX_CANDIDATES = 10
ANGLE_KEEP = 2                        # one viewpoint shot many times: only the best two stay in the gallery


@dataclass
class Item:
    id: int
    feat: F.Feat
    emb: np.ndarray | None = None
    probs: list[tuple[str, float]] | None = None     # best first
    appeal: float = 0.5

    @property
    def score(self) -> float:
        return float(self.feat.quality + 0.1 * (self.appeal - 0.5))


@dataclass
class Result:
    order: list[int] = field(default_factory=list)
    excluded: dict[int, dict] = field(default_factory=dict)          # id -> {dup_of, inliers, d_mean}
    rooms: dict[int, dict] = field(default_factory=dict)             # id -> {label, conf, sure, alts}
    similar: dict[int, list[int]] = field(default_factory=dict)
    scores: dict[int, float] = field(default_factory=dict)
    room_group: dict[int, int] = field(default_factory=dict)


def is_dup(p: F.Pair) -> bool:
    if not p.aspect_ok:
        return False
    if p.ncc >= DUP_NCC:
        return True
    return p.n_in >= DUP_MIN_INLIERS and p.ratio >= DUP_MIN_RATIO and p.d_mean <= DUP_MAX_D_MEAN and p.d_max <= DUP_MAX_D_MAX


def is_similar(p: F.Pair) -> bool:
    return p.aspect_ok and p.n_in >= SIM_MIN_INLIERS and p.ratio >= SIM_MIN_RATIO and p.d_mean <= SIM_MAX_D_MEAN


def same_room(p: F.Pair) -> bool:
    return p.n_in >= ROOM_MIN_INLIERS and p.ratio >= ROOM_MIN_RATIO


def _candidates(items: list[Item]) -> list[tuple[int, int]]:
    n = len(items)
    if n < 2:
        return []
    T = np.stack([it.feat.thumb.ravel() for it in items])
    ncc = (T @ T.T) / T.shape[1]
    sim = ncc.copy()
    if all(it.emb is not None for it in items):
        E = np.stack([it.emb for it in items])
        cos = E @ E.T
        sim = np.maximum(ncc, (cos - 0.75) / 0.25)           # either signal can nominate a pair
        sim[cos < 0.72] = np.minimum(sim[cos < 0.72], ncc[cos < 0.72])
    pairs: set[tuple[int, int]] = set()
    for i in range(n):
        order = [j for j in np.argsort(-sim[i]) if j != i][:MAX_CANDIDATES]
        for j in order:
            if sim[i, j] > 0.2 or n <= 12:
                pairs.add((min(i, j), max(i, j)))
    return sorted(pairs)


def _label(it: Item) -> dict:
    if not it.probs:
        return {"label": "other", "conf": 0.0, "sure": False, "alts": []}
    (l1, p1), (l2, p2) = it.probs[0], it.probs[1]
    return {"label": l1, "conf": round(p1, 3), "sure": bool(p1 >= SURE_P and p1 - p2 >= SURE_MARGIN),
            "alts": [(l, round(p, 3)) for l, p in it.probs[:3]]}


def arrange(items: list[Item]) -> Result:
    res = Result()
    if not items:
        return res
    import cv2
    by_idx = items
    res.scores = {it.id: round(it.score, 4) for it in items}
    res.rooms = {it.id: {**_label(it), "appeal": round(it.appeal, 3)} for it in items}

    # ---- pairwise geometry on likely candidates only
    stats: dict[tuple[int, int], F.Pair] = {}
    for i, j in _candidates(items):
        cv2.setRNGSeed(12345)                                  # RANSAC must give the same answer every run
        stats[(i, j)] = F.compare(items[i].feat, items[j].feat)

    # ---- duplicates: greedy by quality; an excluded photo is always a direct match of its keeper (no chains)
    # (items arrive in file-name order, so a tie - or a near-tie - keeps the first-named copy, never a random one)
    rank = sorted(range(len(items)), key=lambda k: (-round(items[k].score * 20), k))
    assigned: dict[int, int] = {}
    for a in rank:
        if a in assigned:
            continue
        for b in rank:
            if b == a or b in assigned or a in assigned:
                continue
            p = stats.get((min(a, b), max(a, b)))
            if p is not None and is_dup(p):
                assigned[b] = a
                res.excluded[items[b].id] = {"dup_of": items[a].id, "inliers": p.n_in, "d_mean": round(p.d_mean, 4)}
    kept = [k for k in range(len(items)) if k not in assigned]

    # ---- one viewpoint shot many times: keep the best two, set the rest aside (restorable).  A photo joins the
    # cluster of the best photo it looks like (never by chaining), so different angles are never merged.
    clusters: list[list[int]] = []
    for a in sorted(kept, key=lambda k: (-round(items[k].score * 20), k)):
        for cl in clusters:
            p = stats.get((min(a, cl[0]), max(a, cl[0])))
            if p is not None and is_similar(p):
                cl.append(a)
                break
        else:
            clusters.append([a])
    for cl in clusters:
        for b in cl[ANGLE_KEEP:]:
            p = stats[(min(b, cl[0]), max(b, cl[0]))]
            assigned[b] = cl[0]
            res.excluded[items[b].id] = {"dup_of": items[cl[0]].id, "inliers": p.n_in, "d_mean": round(p.d_mean, 4), "kind": "angle"}
    kept = [k for k in kept if k not in assigned]

    # ---- borderline pairs among kept photos -> flagged, never removed
    for (i, j), p in stats.items():
        if i in assigned or j in assigned:
            continue
        if is_similar(p):
            res.similar.setdefault(items[i].id, []).append(items[j].id)
            res.similar.setdefault(items[j].id, []).append(items[i].id)

    # ---- physical rooms: connected components of "these photos share a lot of scene"
    parent = {k: k for k in kept}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for (i, j), p in stats.items():
        if i in parent and j in parent and same_room(p):
            parent[find(i)] = find(j)
    roots = {}
    for k in kept:
        res.room_group[items[k].id] = roots.setdefault(find(k), len(roots))

    res.order = _order(items, kept, res)
    return res


# --------------------------------------------------------------------------- ordering
def _sim(a: Item, b: Item) -> float:
    if a.emb is not None and b.emb is not None:
        return float(np.clip((a.emb @ b.emb - 0.70) / 0.30, 0.0, 1.0))
    return float(np.clip((a.feat.thumb * b.feat.thumb).mean(), 0.0, 1.0))


def _hero(items: list[Item], kept: list[int], res: Result) -> int:
    best, best_v = kept[0], -1.0
    for k in kept:
        it = items[k]
        r = res.rooms[it.id]
        prior = HERO_PRIOR.get(r["label"], 0.2) * (1.0 if r["sure"] else 0.6)
        v = 0.5 * it.score + 0.25 * it.appeal + 0.25 * prior
        if v > best_v:
            best, best_v = k, v
    return best


def _order(items: list[Item], kept: list[int], res: Result) -> list[int]:
    if not kept:
        return []
    hero = _hero(items, kept, res)
    order = [hero]
    chosen = [items[hero]]
    rest = [k for k in kept if k != hero]

    def key(k):
        lab = res.rooms[items[k].id]["label"]
        return (CATEGORY.get(lab, 6), SUBORDER.get(lab, 4))

    buckets: dict[tuple[int, int], list[int]] = {}
    for k in rest:
        buckets.setdefault(key(k), []).append(k)
    for bk in sorted(buckets):
        pool = buckets[bk]
        # physical rooms first (best member decides), then angles within a room spread out by MMR
        groups: dict[int, list[int]] = {}
        for k in pool:
            groups.setdefault(res.room_group[items[k].id], []).append(k)
        for g in sorted(groups.values(), key=lambda m: -max(items[x].score for x in m)):
            left = list(g)
            while left:
                def val(k):
                    pen = max((_sim(items[k], c) for c in chosen), default=0.0)
                    return items[k].score - 0.45 * pen
                nxt = max(left, key=lambda k: (val(k), -k))
                left.remove(nxt)
                order.append(nxt)
                chosen.append(items[nxt])
    return [items[k].id for k in order]
