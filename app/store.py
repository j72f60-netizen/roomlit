"""Job and item state, and everything that touches a job's temporary folder.

Layout of one job (all under DATA_DIR/jobs/<random id>/, never served directly):
    original/<item id>      uploaded photo (opaque name)
    edited/<item id>        enhanced photo
    preview/<id>_*.jpg      before / after / thumbnail previews
    tmp/                    in-flight uploads
    result.zip              built on demand
State is held in memory only; a restart discards everything (by design).

An *apartment set* is the folder that directly contains photos.  Duplicates, room types and the gallery order
are decided per set and never mix photos of different folders.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import posixpath
import re
import secrets
import shutil
import threading
import time
import unicodedata
import zipfile
from dataclasses import dataclass, field

from . import ingest, ordering
from .config import Settings
from .engine.organize.classes import CLASSES

ANGLE_KEEP = 2                     # keep in step with engine/organize/arrange.py (the web process never imports OpenCV)
from .engine.presets import DEFAULT_MODE, PRESETS

log = logging.getLogger("roomlit.store")


DEFAULT_SUFFIX = "بعد التعديل"          # "after editing": added after the folder name the photos came in


def clean_suffix(raw: str | None) -> str:
    """Text appended to the root folder / ZIP name.  Safe on every file system; empty means nothing is added."""
    s = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]|\.{2,}', " ", raw or "")
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", s).strip(" ."))[:40].strip(" .")


class JobError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


@dataclass
class Item:
    id: int
    parts: list[str]                 # sanitised client path, root folder first
    size: int
    group: str                       # folder that directly contains the photo (= apartment set key)
    out_rel: str                     # original relative path (extension adjusted only when the format must change)
    set_id: int = 0
    status: str = "uploaded"         # uploaded|analyzing|ready|queued|processing|done|failed
    mode: str | None = None
    error: str | None = None
    width: int = 0
    height: int = 0
    out_bytes: int = 0
    seconds: float = 0.0
    version: int = 0
    analysis: dict | None = None
    # --- organisation
    organized: bool = False
    room: str | None = None          # room type shown to the user (a suggestion until the user sets it)
    room_conf: float = 0.0
    room_sure: bool = False
    room_alts: list = field(default_factory=list)
    room_user: bool = False          # the user chose this label
    room_group: int = 0
    score: float = 0.5
    appeal: float = 0.5
    similar: list[int] = field(default_factory=list)
    auto_excluded: bool = False      # a better photo of the same shot exists
    dup_of: int | None = None
    ex_kind: str = "dup"             # why the organizer set it aside: 'dup' (same shot) | 'angle' (more than the best two of one angle)
    user_state: str | None = None    # 'keep' (restored) | 'exclude' (removed by the user)
    sha: str = ""                    # SHA-256 of the uploaded bytes (recognises the very same file arriving twice)
    retouch: list = field(default_factory=list)      # the user's strokes (remove / smooth), see engine/retouch_ops.py

    @property
    def name(self) -> str:
        return self.parts[-1]

    @property
    def renamed(self) -> bool:
        """True only when two *different* files had the same path, so one of them could not keep its exact name."""
        return posixpath.basename(self.out_rel) != self.name

    @property
    def excluded(self) -> bool:
        return self.user_state == "exclude" or (self.user_state != "keep" and self.auto_excluded)

    @property
    def included(self) -> bool:
        return self.status != "failed" and not self.excluded


@dataclass
class PSet:
    id: int
    key: str                         # folder path including the root, e.g. "Al Khuzama/1"
    order: list[int] = field(default_factory=list)       # included photo ids, gallery order, first = main photo
    manual: bool = False             # the user arranged it by hand
    organized: bool = False

    @property
    def label(self) -> str:
        parts = self.key.split("/")
        return "/".join(parts[1:]) if len(parts) > 1 else parts[0]


@dataclass
class Job:
    id: str
    owner: str
    root: str
    mode: str
    created: float
    last_activity: float
    items: dict[int, Item] = field(default_factory=dict)
    sets: dict[int, PSet] = field(default_factory=dict)
    set_by_key: dict[str, int] = field(default_factory=dict)
    taken: set[str] = field(default_factory=set)
    next_id: int = 1
    next_set: int = 1
    rev: int = 1
    ignored: dict[str, int] = field(default_factory=dict)
    bytes_total: int = 0
    edit_version: int = 0
    arr_version: int = 0
    zip_key: tuple | None = None
    downloaded_at: float | None = None
    failed_at: float | None = None
    purged: bool = False
    deleting: bool = False
    organizing: bool = False
    smart: bool = True               # remove same-shot copies and arrange for Airbnb/Booking; False = keep every photo in name order
    ml: bool | None = None           # was the room model available for the last organisation?
    lock: threading.RLock = field(default_factory=threading.RLock)
    zip_lock: threading.Lock = field(default_factory=threading.Lock)

    def bump(self) -> None:
        self.rev += 1

    def touch(self) -> None:
        self.last_activity = time.time()

    # paths
    def p_original(self, item_id: int) -> str:
        return os.path.join(self.root, "original", str(item_id))

    def p_edited(self, item_id: int) -> str:
        return os.path.join(self.root, "edited", str(item_id))

    @property
    def p_preview(self) -> str:
        return os.path.join(self.root, "preview")

    @property
    def p_tmp(self) -> str:
        return os.path.join(self.root, "tmp")

    @property
    def p_zip(self) -> str:
        return os.path.join(self.root, "result.zip")


def _rm(p: str) -> None:
    try:
        os.remove(p)
    except OSError:
        pass


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def name_key(name: str, ident: int = 0):
    """File-manager order: numbers count as numbers (IMG_2 before IMG_10) and the name is compared before the
    extension (IMG_1.jpg before IMG_1 copy.jpg).  Fully deterministic: it never depends on upload timing."""
    stem, ext = os.path.splitext(name)
    return (natural_key(stem), natural_key(ext), name, ident)


class JobStore:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self.wipe_all()

    # ------------------------------------------------------------ lifecycle
    def wipe_all(self) -> None:
        """Start from nothing: no photo may survive a restart."""
        shutil.rmtree(self.cfg.jobs_dir, ignore_errors=True)
        os.makedirs(self.cfg.jobs_dir, mode=0o700, exist_ok=True)

    def create(self, owner: str, mode: str) -> Job:
        if mode not in PRESETS:
            mode = DEFAULT_MODE
        with self._lock:
            live = [j for j in self.jobs.values() if not j.deleting]
            if len(live) >= self.cfg.max_jobs:
                raise JobError(429, "too_many_jobs", "Too many jobs are open. Delete a finished job first.")
            self._check_disk()
            jid = secrets.token_urlsafe(18)
            root = os.path.join(self.cfg.jobs_dir, jid)
            for sub in ("original", "edited", "preview", "tmp"):
                os.makedirs(os.path.join(root, sub), mode=0o700)
            now = time.time()
            job = Job(id=jid, owner=owner, root=root, mode=mode, created=now, last_activity=now)
            self.jobs[jid] = job
            return job

    def get(self, job_id: str, owner: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None or job.owner != owner or job.deleting:
            raise JobError(404, "job_not_found", "This job no longer exists (it may have expired).")
        return job

    def list_for(self, owner: str) -> list[Job]:
        return sorted((j for j in self.jobs.values() if j.owner == owner and not j.deleting),
                      key=lambda j: j.created, reverse=True)

    def delete(self, job: Job) -> None:
        with job.lock:
            job.deleting = True
        with self._lock:
            self.jobs.pop(job.id, None)
        shutil.rmtree(job.root, ignore_errors=True)
        log.info("job %s deleted", job.id[:6])

    def purge_files(self, job: Job) -> None:
        """Drop every photo of a job but keep its (photo-free) status so the UI can explain what happened."""
        with job.lock:
            for sub in ("original", "edited", "preview", "tmp"):
                shutil.rmtree(os.path.join(job.root, sub), ignore_errors=True)
                os.makedirs(os.path.join(job.root, sub), mode=0o700, exist_ok=True)
            _rm(job.p_zip)
            job.purged = True
            job.bump()

    # ------------------------------------------------------------ disk guards
    def free_mb(self) -> float:
        return shutil.disk_usage(self.cfg.data_dir).free / 1e6

    def _check_disk(self) -> None:
        if self.free_mb() < self.cfg.min_free_disk_mb:
            raise JobError(507, "disk_full", "The server is out of temporary space. Delete finished jobs and try again.")

    def new_tmp_path(self, job: Job) -> str:
        return os.path.join(job.p_tmp, secrets.token_hex(12))

    # ------------------------------------------------------------ items
    def add_item(self, job: Job, parts: list[str], tmp_path: str, size: int, sha: str = "") -> Item | None:
        """Register a validated photo.  Moves `tmp_path` into the job as an opaque file name.

        Returns None when this very file (same path, same bytes) is already in the job: a retried request or the same
        folder added twice must never create a second photo."""
        with job.lock:
            if job.deleting:
                _rm(tmp_path)
                raise JobError(404, "job_not_found")
            if sha:
                path_key = unicodedata.normalize("NFC", "/".join(ingest.with_root(parts))).lower()
                for other in job.items.values():
                    if other.sha == sha and unicodedata.normalize("NFC", "/".join(other.parts)).lower() == path_key:
                        _rm(tmp_path)
                        job.ignored["same_file"] = job.ignored.get("same_file", 0) + 1
                        job.bump()
                        return None
            if len(job.items) >= self.cfg.max_files_per_job:
                _rm(tmp_path)
                raise JobError(413, "too_many_files",
                               f"A job can hold up to {self.cfg.max_files_per_job} photos. Process these, then start a new job.")
            if job.bytes_total + size > self.cfg.max_job_mb * 1_000_000:
                _rm(tmp_path)
                raise JobError(413, "job_too_large",
                               f"A job can hold up to {self.cfg.max_job_mb} MB of photos. Process these, then start a new job.")
            parts = ingest.with_root(parts)
            item_id = job.next_id
            job.next_id += 1
            group = ingest.group_of(parts)
            sid = job.set_by_key.get(group)
            if sid is None:
                sid = job.next_set
                job.next_set += 1
                job.set_by_key[group] = sid
                job.sets[sid] = PSet(id=sid, key=group)
            out = ingest.dedupe(ingest.out_rel_for(parts), job.taken)
            item = Item(id=item_id, parts=parts, size=size, group=group, out_rel=out, set_id=sid, sha=sha)
            os.replace(tmp_path, job.p_original(item_id))
            job.items[item_id] = item
            job.bytes_total += size
            job.bump()
            job.touch()
            return item

    def remove_item_files(self, job: Job, item: Item, *, original: bool = True) -> None:
        if original:
            _rm(job.p_original(item.id))
        _rm(job.p_edited(item.id))
        for kind in ("before", "after", "thumb"):
            _rm(os.path.join(job.p_preview, f"{item.id}_{kind}.jpg"))

    # ------------------------------------------------------------ organisation
    def sets_needing_organization(self, job: Job) -> list[PSet]:
        with job.lock:
            ids = {i.set_id for i in job.items.values() if not i.organized and i.status in ("ready", "queued", "done")}
            return [job.sets[s] for s in sorted(ids)]

    def organizer_payload(self, job: Job, pset: PSet) -> dict:
        with job.lock:
            members = sorted((i for i in job.items.values()
                               if i.set_id == pset.id and i.status in ("ready", "queued", "done") and i.analysis),
                             key=lambda i: name_key(i.name, i.id))          # file-name order: ties never depend on arrival
            items = [{"id": i.id, "preview": os.path.join(job.p_preview, f"{i.id}_before.jpg"),
                      "analysis": i.analysis or {}, "pixels": i.width * i.height} for i in members]
        return {"id": pset.id, "items": items}

    def apply_organization(self, job: Job, pset: PSet, res: dict | None) -> None:
        """Store the organizer's suggestions.  Anything the user already decided is left alone."""
        with job.lock:
            members = [i for i in job.items.values() if i.set_id == pset.id and i.status != "failed"]
            if res is None:     # organizer unavailable: keep everything, natural file order
                for it in members:
                    it.organized = True
                    it.auto_excluded = False
                    it.dup_of = None
                if not pset.manual:
                    pset.order = [i.id for i in sorted((m for m in members if m.included), key=lambda i: name_key(i.name, i.id))]
                self._fix_order(job, pset)
                pset.organized = True
                job.arr_version += 1
                job.bump()
                return
            ex = {int(k): v for k, v in res["excluded"].items()}
            scores = {int(k): v for k, v in res["scores"].items()}
            rooms = {int(k): v for k, v in res["rooms"].items()}
            groups = {int(k): v for k, v in res["room_group"].items()}
            similar = {int(k): v for k, v in res["similar"].items()}
            for it in members:
                it.organized = True
                if it.id not in scores:
                    continue
                it.score = float(scores[it.id])
                r = rooms[it.id]
                it.appeal = float(r.get("appeal", it.appeal))
                if not it.room_user:
                    it.room, it.room_conf, it.room_sure, it.room_alts = r["label"], r["conf"], r["sure"], r["alts"]
                it.room_group = int(groups.get(it.id, 0))
                it.similar = list(similar.get(it.id, []))
                if it.id in ex:
                    it.auto_excluded, it.dup_of, it.ex_kind = True, ex[it.id]["dup_of"], ex[it.id].get("kind", "dup")
                else:
                    it.auto_excluded, it.dup_of, it.ex_kind = False, None, "dup"
            if pset.manual:
                self._fix_order(job, pset, preferred=res["order"])
            else:
                pset.order = [i for i in res["order"] if i in job.items and job.items[i].included]
                self._fix_order(job, pset)
            pset.organized = True
            job.arr_version += 1
            job.bump()

    def _fix_order(self, job: Job, pset: PSet, preferred: list[int] | None = None) -> None:
        """Make `pset.order` contain exactly the included photos: drop excluded ones, add missing ones sensibly."""
        inc = [i for i in job.items.values() if i.set_id == pset.id and i.included]
        inc_ids = {i.id for i in inc}
        order = [i for i in pset.order if i in inc_ids]
        have = set(order)
        pref_rank = {i: n for n, i in enumerate(preferred or [])}
        for it in sorted((i for i in inc if i.id not in have), key=lambda i: (pref_rank.get(i.id, 10 ** 6), name_key(i.name, i.id))):
            if it.dup_of in order and it.user_state == "keep":
                order.insert(order.index(it.dup_of) + 1, it.id)      # a restored duplicate goes right after its twin
            else:
                order.append(it.id)
            have.add(it.id)
        pset.order = order

    def set_exclude(self, job: Job, item: Item) -> list[Item]:
        """Remove a photo from the final gallery.  Returns photos promoted so that its angle is still covered."""
        promoted: list[Item] = []
        with job.lock:
            item.user_state = "exclude"
            dups = [i for i in job.items.values()
                    if i.dup_of == item.id and i.auto_excluded and i.user_state != "exclude"]
            if dups:
                best = max(dups, key=lambda i: i.score)
                best.auto_excluded, best.dup_of, best.user_state = False, None, "keep"
                for o in dups:
                    if o is not best:
                        o.dup_of = best.id
                promoted.append(best)
            self._fix_order(job, job.sets[item.set_id])
            job.arr_version += 1
            job.bump()
        return promoted

    def set_restore(self, job: Job, item: Item) -> None:
        with job.lock:
            item.user_state = "keep"
            self._fix_order(job, job.sets[item.set_id])
            job.arr_version += 1
            job.bump()

    def set_order(self, job: Job, pset: PSet, order: list[int]) -> None:
        with job.lock:
            if sorted(order) != sorted(pset.order):
                raise JobError(409, "order_mismatch", "The photo list changed. Refresh and try again.")
            pset.order = list(order)
            pset.manual = True
            job.arr_version += 1
            job.bump()

    def make_main(self, job: Job, item: Item) -> None:
        with job.lock:
            pset = job.sets[item.set_id]
            if item.id not in pset.order:
                raise JobError(409, "not_in_gallery", "Restore this photo first.")
            pset.order = [item.id] + [i for i in pset.order if i != item.id]
            pset.manual = True
            job.arr_version += 1
            job.bump()

    def set_retouch(self, job: Job, item: Item, ops: list) -> None:
        with job.lock:
            item.retouch = list(ops)
            job.bump()

    def set_room(self, job: Job, item: Item, room: str) -> None:
        if room not in CLASSES:
            raise JobError(400, "bad_room", "Unknown room type")
        with job.lock:
            item.room, item.room_user, item.room_sure, item.room_conf = room, True, True, 1.0
            job.bump()

    def reset_order(self, job: Job, pset: PSet) -> None:
        """Original (file-name) order, or in smart mode the suggested Airbnb order (reflects corrected room labels)."""
        with job.lock:
            inc = [i for i in job.items.values() if i.set_id == pset.id and i.included]
            if not job.smart:                                  # plain mode: back to file-name order, nothing arranged
                pset.order = [i.id for i in sorted(inc, key=lambda i: name_key(i.name, i.id))]
            else:
                pset.order = ordering.simple_order([
                    {"id": i.id, "label": i.room or "other", "sure": i.room_sure, "score": i.score,
                     "appeal": i.appeal, "group": i.room_group} for i in inc])
            pset.manual = False
            job.arr_version += 1
            job.bump()

    # ------------------------------------------------------------ public view
    def counts(self, job: Job) -> dict[str, int]:
        c = {"total": 0, "uploaded": 0, "analyzing": 0, "ready": 0, "queued": 0, "processing": 0, "done": 0, "failed": 0}
        for it in job.items.values():
            c["total"] += 1
            c[it.status] += 1
        return c

    def expires_in(self, job: Job) -> int:
        ttl = self.cfg.downloaded_ttl_minutes if job.downloaded_at else self.cfg.job_ttl_minutes
        base = max(job.last_activity, job.downloaded_at or 0.0)
        if job.failed_at:
            ttl = min(ttl, self.cfg.failed_ttl_minutes)
            base = max(base, job.failed_at)
        return max(0, int(base + ttl * 60 - time.time()))

    def public(self, job: Job) -> dict:
        with job.lock:
            counts = self.counts(job)
            to_start = sum(1 for i in job.items.values() if i.status in ("uploaded", "analyzing", "ready") and not i.excluded)
            counts["to_start"] = to_start
            counts["excluded"] = sum(1 for i in job.items.values() if i.excluded and i.status != "failed")
            counts["final"] = sum(1 for i in job.items.values() if i.included)
            counts["renamed"] = sum(1 for i in job.items.values() if i.renamed)
            pos: dict[int, int] = {}
            for s in job.sets.values():
                for n, iid in enumerate(s.order, 1):
                    pos[iid] = n
            items = []
            for it in sorted(job.items.values(), key=lambda i: (natural_key(i.group), pos.get(i.id, 10 ** 6), name_key(i.name, i.id))):
                items.append({
                    "id": it.id, "name": it.name, "dir": it.group, "set": it.set_id, "status": it.status,
                    "mode": it.mode, "w": it.width, "h": it.height, "err": it.error,
                    "v": it.version, "bytes": it.out_bytes, "src_bytes": it.size,
                    "out": it.out_rel, "sec": it.seconds,
                    "pos": pos.get(it.id, 0), "ex": it.excluded and it.status != "failed",
                    "ex_why": ("user" if it.user_state == "exclude" else it.ex_kind) if it.excluded else None,
                    "dup_of": it.dup_of if it.excluded and it.user_state != "exclude" else None,
                    "restored": it.user_state == "keep",
                    "room": it.room, "room_conf": round(it.room_conf, 2), "room_sure": it.room_sure,
                    "room_alts": it.room_alts, "room_user": it.room_user,
                    "similar": it.similar, "org": it.organized, "renamed": it.renamed, "rt": len(it.retouch),
                })
            sets = [{"id": s.id, "key": s.key, "label": s.label, "organized": s.organized, "manual": s.manual,
                     "order": list(s.order)} for s in sorted(job.sets.values(), key=lambda s: natural_key(s.key))]
            working = counts["queued"] + counts["processing"]
            if counts["total"] == 0:
                phase = "empty"
            elif job.organizing and not working:
                phase = "organizing"
            elif working or job.organizing:
                phase = "processing"
            elif counts["uploaded"] or counts["analyzing"]:
                phase = "preparing"
            elif to_start:
                phase = "partial" if counts["done"] else "ready"
            else:
                phase = "done" if counts["done"] else "failed"
            roots = sorted({i.parts[0] for i in job.items.values()}, key=natural_key)
            return {
                "id": job.id, "rev": job.rev, "mode": job.mode, "phase": phase, "counts": counts,
                "ignored": dict(job.ignored), "already": job.ignored.get("same_file", 0),
                "ignored_total": sum(v for k, v in job.ignored.items() if k != "same_file"), "smart": job.smart,
                "expires_in": self.expires_in(job), "downloaded": bool(job.downloaded_at),
                "purged": job.purged, "created": int(job.created), "items": items, "sets": sets,
                "roots": roots, "zip_name": self.zip_name(job), "ml": job.ml, "rooms": CLASSES,
            }

    def summary(self, job: Job) -> dict:
        counts = self.counts(job)
        return {"id": job.id, "created": int(job.created), "mode": job.mode, "counts": counts,
                "expires_in": self.expires_in(job), "purged": job.purged}

    # ------------------------------------------------------------ zip + log
    @staticmethod
    def zip_name(job: Job, suffix: str = "") -> str:
        """`<folder name> <suffix>.zip` (one root folder) - the same name the folder inside the ZIP gets."""
        roots = {i.parts[0] for i in job.items.values()}
        suffix = clean_suffix(suffix)
        if len(roots) == 1:
            return f"{next(iter(roots))} {suffix}".strip() + ".zip"
        return "Roomlit export.zip"

    @staticmethod
    def _rename_root(rel_dir: str, suffix: str) -> str:
        if not suffix:
            return rel_dir
        first, _, rest = rel_dir.partition("/")
        return posixpath.join(f"{first} {suffix}", rest) if rest else f"{first} {suffix}"

    @staticmethod
    def final_name(item: Item, n: int, digits: int, numbering: bool) -> str:
        base = posixpath.basename(item.out_rel)
        return f"{n:0{digits}d} - {base}" if numbering else base

    def plan_zip(self, job: Job, numbering: bool, suffix: str = "") -> tuple[list[tuple[str, Item]], list[dict]]:
        """(zip entries in gallery order, log rows).  Only finished, included photos are delivered.
        The root folder is called `<original name> <suffix>`; sub-folders and file names are as uploaded."""
        suffix = clean_suffix(suffix)
        entries: list[tuple[str, Item]] = []
        rows: list[dict] = []
        with job.lock:
            for pset in sorted(job.sets.values(), key=lambda s: natural_key(s.key)):
                deliver = [job.items[i] for i in pset.order
                           if i in job.items and job.items[i].status == "done" and os.path.exists(job.p_edited(i))]
                digits = max(2, len(str(len(deliver))))
                final: dict[int, tuple[int, str]] = {}
                for n, it in enumerate(deliver, 1):
                    arc = posixpath.join(self._rename_root(posixpath.dirname(it.out_rel), suffix), self.final_name(it, n, digits, numbering))
                    entries.append((arc, it))
                    final[it.id] = (n, arc)
                for it in sorted((i for i in job.items.values() if i.set_id == pset.id),
                                 key=lambda i: (final.get(i.id, (10 ** 6,))[0], name_key(i.name, i.id))):
                    delivered = it.id in final
                    if it.status == "failed":
                        status, why = "failed", it.error or ""
                    elif it.excluded:
                        status = "excluded"
                        keeper = job.items.get(it.dup_of) if it.dup_of else None
                        if it.user_state == "exclude":
                            why = "Removed by user"
                        elif keeper:
                            why = (f"Same angle as {keeper.name} (kept the best {ANGLE_KEEP})" if it.ex_kind == "angle"
                                   else f"Same shot as {keeper.name} (kept the better photo)")
                        else:
                            why = "Duplicate"
                    elif delivered:
                        status, why = "included", ""
                    else:
                        status, why = "not delivered", "not processed yet"
                    rows.append({
                        "apartment_folder": pset.key, "final_position": final[it.id][0] if delivered else "",
                        "final_file": final[it.id][1].rsplit("/", 1)[-1] if delivered else "",
                        "final_path": final[it.id][1] if delivered else "",
                        "original_file": it.name, "original_path": "/".join(it.parts),
                        "room_type": it.room or "", "room_confidence": f"{it.room_conf:.2f}" if it.room else "",
                        "room_set_by_user": "yes" if it.room_user else "no",
                        "main_photo": "yes" if delivered and final[it.id][0] == 1 else "",
                        "status": status, "reason": why,
                        "similar_to": "; ".join(job.items[s].name for s in it.similar if s in job.items),
                        "edit_mode": it.mode or "",
                    })
        return entries, rows

    @staticmethod
    def log_csv(rows: list[dict]) -> bytes:
        cols = ["apartment_folder", "final_position", "final_file", "final_path", "original_file", "original_path", "room_type",
                "room_confidence", "room_set_by_user", "main_photo", "status", "reason", "similar_to", "edit_mode"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
        return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")       # BOM: Excel shows Arabic names correctly

    def log_for(self, job: Job, numbering: bool = True, suffix: str = "") -> bytes:
        return self.log_csv(self.plan_zip(job, numbering, suffix)[1])

    def build_zip(self, job: Job, numbering: bool = True, suffix: str = "") -> str:
        """Create (or reuse) the result ZIP: `<root> <suffix>/` + original sub-folders, photos in their final order.
        The ZIP holds photos only (the log is a separate download)."""
        suffix = clean_suffix(suffix)
        with job.lock:
            if job.organizing or any(i.status in ("queued", "processing") for i in job.items.values()):
                raise JobError(409, "still_working", "Some photos are still being edited. Download when they are finished.")
        with job.zip_lock:
            key = (job.edit_version, job.arr_version, numbering, suffix)
            if job.zip_key == key and os.path.exists(job.p_zip):
                return job.p_zip
            entries, _ = self.plan_zip(job, numbering, suffix)
            if not entries:
                raise JobError(409, "nothing_to_download", "There are no edited photos to download yet.")
            names = [unicodedata.normalize("NFC", arc).lower() for arc, _ in entries]
            if len(set(names)) != len(names) or len({it.id for _, it in entries}) != len(entries):
                raise JobError(500, "zip_inconsistent", "Could not build the ZIP safely. Please re-edit and try again.")
            tmp = job.p_zip + ".part"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
                for arc, it in entries:
                    zf.write(job.p_edited(it.id), arc)
            os.replace(tmp, job.p_zip)
            job.zip_key = key
            return job.p_zip

    # ------------------------------------------------------------ expiry
    def expired(self) -> list[Job]:
        out = []
        for job in list(self.jobs.values()):
            if self.expires_in(job) <= 0 and not self._busy(job):
                out.append(job)
        return out

    @staticmethod
    def _busy(job: Job) -> bool:
        return job.organizing or any(i.status in ("queued", "processing") for i in job.items.values())
