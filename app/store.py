"""Job and item state, and everything that touches a job's temporary folder.

Layout of one job (all under DATA_DIR/jobs/<random id>/, never served directly):
    original/<item id>      uploaded photo (opaque name)
    edited/<item id>        enhanced photo
    preview/<id>_*.jpg      before / after / thumbnail previews
    tmp/                    in-flight uploads
    result.zip              built on demand
State is held in memory only; a restart discards everything (by design).
"""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import threading
import time
import unicodedata
import zipfile
from dataclasses import dataclass, field

from . import ingest
from .config import Settings
from .engine.presets import DEFAULT_MODE, PRESETS

log = logging.getLogger("roomlit.store")


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
    group: str
    out_rel: str
    status: str = "uploaded"         # uploaded|analyzing|ready|queued|processing|done|failed
    mode: str | None = None
    error: str | None = None
    width: int = 0
    height: int = 0
    out_bytes: int = 0
    seconds: float = 0.0
    version: int = 0
    analysis: dict | None = None

    @property
    def name(self) -> str:
        return self.parts[-1]


@dataclass
class Job:
    id: str
    owner: str
    root: str
    mode: str
    created: float
    last_activity: float
    items: dict[int, Item] = field(default_factory=dict)
    taken: set[str] = field(default_factory=set)
    next_id: int = 1
    rev: int = 1
    ignored: dict[str, int] = field(default_factory=dict)
    bytes_total: int = 0
    edit_version: int = 0
    zip_version: int = -1
    downloaded_at: float | None = None
    failed_at: float | None = None
    purged: bool = False
    deleting: bool = False
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
    def add_item(self, job: Job, parts: list[str], tmp_path: str, size: int) -> Item:
        """Register a validated photo.  Moves `tmp_path` into the job as an opaque file name."""
        with job.lock:
            if job.deleting:
                _rm(tmp_path)
                raise JobError(404, "job_not_found")
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
            out = ingest.dedupe(ingest.out_rel_for(parts, ingest.out_ext_for(parts[-1])), job.taken)
            item = Item(id=item_id, parts=parts, size=size, group=ingest.group_of(parts), out_rel=out)
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

    def retarget_ext(self, job: Job, item: Item, out_ext: str) -> None:
        """The decoded format decides the output extension (e.g. a JPEG that was named .png)."""
        cur = os.path.splitext(item.out_rel)[1].lower()
        same = {".jpg": {".jpg", ".jpeg"}, ".png": {".png"}, ".webp": {".webp"}, ".tif": {".tif", ".tiff"}}
        if cur in same.get(out_ext, {out_ext}):
            return
        with job.lock:
            job.taken.discard(unicodedata.normalize("NFC", item.out_rel).lower())
            item.out_rel = ingest.dedupe(ingest.out_rel_for(item.parts, out_ext), job.taken)

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
            items = []
            for it in sorted(job.items.values(), key=lambda i: (i.group.lower(), i.name.lower(), i.id)):
                items.append({
                    "id": it.id, "name": it.name, "dir": it.group, "status": it.status,
                    "mode": it.mode, "w": it.width, "h": it.height, "err": it.error,
                    "v": it.version, "bytes": it.out_bytes, "src_bytes": it.size,
                    "out": it.out_rel, "sec": it.seconds,
                })
            busy = counts["uploaded"] + counts["analyzing"] + counts["queued"] + counts["processing"]
            if counts["total"] == 0:
                phase = "empty"
            elif busy and (counts["queued"] or counts["processing"]):
                phase = "processing"
            elif counts["uploaded"] or counts["analyzing"]:
                phase = "preparing"
            elif counts["ready"] and not counts["done"]:
                phase = "ready"
            elif counts["ready"]:
                phase = "partial"
            else:
                phase = "done" if counts["done"] else "failed"
            return {
                "id": job.id, "rev": job.rev, "mode": job.mode, "phase": phase, "counts": counts,
                "ignored": dict(job.ignored), "ignored_total": sum(job.ignored.values()),
                "expires_in": self.expires_in(job), "downloaded": bool(job.downloaded_at),
                "purged": job.purged, "created": int(job.created), "items": items,
            }

    def summary(self, job: Job) -> dict:
        counts = self.counts(job)
        return {"id": job.id, "created": int(job.created), "mode": job.mode, "counts": counts,
                "expires_in": self.expires_in(job), "purged": job.purged}

    # ------------------------------------------------------------ zip
    def build_zip(self, job: Job) -> str:
        """Create (or reuse) the organised result ZIP.  Photos are already compressed, so entries are stored."""
        with job.zip_lock:
            with job.lock:
                version = job.edit_version
                done = [it for it in job.items.values() if it.status == "done"]
            if not done:
                raise JobError(409, "nothing_to_download", "There are no edited photos to download yet.")
            if job.zip_version == version and os.path.exists(job.p_zip):
                return job.p_zip
            tmp = job.p_zip + ".part"
            used: set[str] = set()
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
                for it in sorted(done, key=lambda i: i.out_rel.lower()):
                    src = job.p_edited(it.id)
                    if not os.path.exists(src):
                        continue
                    arc = ingest.dedupe(it.out_rel, used)
                    zf.write(src, arc)
            os.replace(tmp, job.p_zip)
            job.zip_version = version
            return job.p_zip

    # ------------------------------------------------------------ expiry
    def expired(self) -> list[Job]:
        now = time.time()
        out = []
        for job in list(self.jobs.values()):
            if self.expires_in(job) <= 0 and not self._busy(job):
                out.append(job)
        return out

    @staticmethod
    def _busy(job: Job) -> bool:
        return any(i.status in ("queued", "processing") for i in job.items.values())
