"""Controlled, sequential processing.

One worker process handles one photo at a time (low, predictable memory).  The dispatcher feeds it from a FIFO
queue, so analysis tasks queued at upload always run before the "organize" and processing tasks queued by Start.

Organising (duplicates, room types, order) loads an 89 MB model, so it runs in a *second*, short-lived process
and the image worker is stopped meanwhile: only one heavy process exists at any moment (512 MB server).
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import multiprocessing as mp
import os
import time

from . import ingest
from .config import Settings
from .engine.presets import DEFAULT_MODE, PRESETS
from .store import Item, Job, JobStore, natural_key

log = logging.getLogger("roomlit.runner")

ENLARGE_TO = 2048            # Airbnb's recommended long edge; smaller photos are enlarged to it when "enhance resolution" is on


class WorkerError(Exception):
    """Worker-level failure with a message that is safe to show to the user."""


class ImageProblem(Exception):
    """The photo itself is the problem (corrupt, unsupported, too large)."""


class WorkerProc:
    def __init__(self, cfg: Settings, kind: str = "image"):
        self.cfg = cfg
        self.kind = kind
        self._ctx = mp.get_context("spawn")
        self._proc = None
        self._conn = None
        self._tasks = 0
        self.pid: int | None = None
        self.peak_mb: float = 0.0

    def _start(self) -> None:
        self.close()
        parent, child = self._ctx.Pipe()
        if self.kind == "ml":
            from .worker_ml_main import main
            args = (child, self.cfg.model_dir, self.cfg.cv_threads)
        else:
            from .worker_main import main
            args = (child, self.cfg.max_pixels, self.cfg.cv_threads)
        proc = self._ctx.Process(target=main, args=args, daemon=True)
        proc.start()
        child.close()
        if not parent.poll(60):
            proc.kill()
            raise WorkerError("The worker failed to start")
        parent.recv()
        self._proc, self._conn, self._tasks, self.pid = proc, parent, 0, proc.pid

    def _sample_peak(self) -> None:
        """Highest resident memory the worker has reached (Linux /proc)."""
        try:
            with open(f"/proc/{self.pid}/status") as f:
                for line in f:
                    if line.startswith("VmHWM:"):
                        self.peak_mb = max(self.peak_mb, round(int(line.split()[1]) / 1024, 1))
        except OSError:
            pass

    def close(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.is_alive():
                    self._proc.kill()
                self._proc.join(2)
            except Exception:
                pass
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._proc = self._conn = self.pid = None

    def call(self, fn: str, args: tuple, timeout: float):
        """Blocking.  Returns the result or raises WorkerError / ImageProblem."""
        if self._proc is None or not self._proc.is_alive() or self._tasks >= self.cfg.worker_recycle:
            self._start()
        self._tasks += 1
        try:
            self._conn.send((fn, args))
            if not self._conn.poll(timeout):
                self._sample_peak()
                self.close()
                raise WorkerError("This photo took too long to process and was skipped")
            kind, payload = self._conn.recv()
            self._sample_peak()
        except (EOFError, BrokenPipeError, ConnectionError, OSError):
            self.close()
            raise WorkerError("The server ran out of memory on this photo. It is probably too large; edit it separately.")
        if kind == "ok":
            return payload
        if kind == "image_error":
            raise ImageProblem(payload)
        log.error("worker error: %s", payload.splitlines()[-1] if payload else "?")
        raise WorkerError("An unexpected error occurred while processing this photo")


class Dispatcher:
    def __init__(self, cfg: Settings, store: JobStore):
        self.cfg = cfg
        self.store = store
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self.worker = WorkerProc(cfg)
        self.ml = WorkerProc(cfg, "ml")
        self._task: asyncio.Task | None = None
        self.busy = False

    def start(self) -> None:
        self.queue = asyncio.PriorityQueue()  # bound to the running event loop (matters if the app is started twice)
        self.busy = False
        self._task = asyncio.create_task(self._run(), name="dispatcher")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await asyncio.to_thread(self.worker.close)
        await asyncio.to_thread(self.ml.close)

    @property
    def pending(self) -> int:
        return self.queue.qsize() + (1 if self.busy else 0)

    # -------------------------------------------------------------- enqueue
    def _put(self, prio: int, kind: str, job: Job, item_id: int | None, mode: str | None) -> None:
        """prio 0 = what the user is waiting for (FIFO among themselves); prio 1 = background work that yields to it."""
        self.queue.put_nowait((prio, next(self._seq), kind, job, item_id, mode))

    def enqueue_analyze(self, job: Job, item: Item) -> None:
        self._put(0, "analyze", job, item.id, None)

    def enqueue_process(self, job: Job, item: Item, mode: str) -> None:
        with job.lock:
            item.status = "queued"
            item.mode = mode
            item.error = None
            job.bump()
        self._put(0, "process", job, item.id, mode)

    # -------------------------------------------------------------- loop
    async def _run(self) -> None:
        while True:
            _, _, kind, job, item_id, mode = await self.queue.get()
            self.busy = True
            try:
                if job.deleting:
                    continue
                if kind == "organize":
                    await self._organize(job, mode)
                    continue
                item = job.items.get(item_id)
                if item is None:
                    continue
                if kind == "analyze":
                    await self._analyze(job, item)
                elif kind == "preedit":
                    await self._preedit(job, item, mode)
                else:
                    await self._process(job, item, mode)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("dispatcher error")
                if kind == "organize":
                    job.organizing = False
            finally:
                self.busy = False
                self.queue.task_done()
                self._after(job)

    def _after(self, job: Job) -> None:
        """If a deletion raced with a running task, make sure nothing is left behind."""
        if job.deleting:
            import shutil
            shutil.rmtree(job.root, ignore_errors=True)
            return
        c = self.store.counts(job)
        if c["total"] and c["failed"] == c["total"] and not job.purged:
            with job.lock:
                job.failed_at = time.time()
            self.store.purge_files(job)
            log.info("job %s failed entirely; files removed", job.id[:6])

    async def _analyze(self, job: Job, item: Item) -> None:
        with job.lock:
            if item.status != "uploaded":
                return
            item.status = "analyzing"
            job.bump()
        try:
            res = await asyncio.to_thread(
                self.worker.call, "analyze",
                (job.p_original(item.id), job.p_preview, item.id, self.cfg.max_pixels), 120)
        except (ImageProblem, WorkerError) as e:
            self._fail(job, item, str(e), drop_original=True)
            return
        with job.lock:
            item.width, item.height = res["width"], res["height"]
            item.analysis = res["analysis"]
            item.status = "ready"
            job.bump()

    async def _organize(self, job: Job, mode: str) -> None:
        """Decide the final order of every apartment folder that has new photos, then queue the edits.

        Smart (default): same-shot copies are set aside (restorable) and the gallery is arranged for Airbnb / Booking.
        Plain (the user unticked it): every photo is kept, in file-manager name order."""
        t0 = time.time()
        sets = self.store.sets_needing_organization(job)
        results: dict | None = None
        if sets and not job.smart:
            for s in sets:
                self.store.apply_organization(job, s, None)
            job.ml = None
        elif sets:
            payload = [self.store.organizer_payload(job, s) for s in sets]
            try:
                await asyncio.to_thread(self.worker.close)          # never two heavy processes at once
                results = await asyncio.to_thread(self.ml.call, "organize", (payload,), self.cfg.organize_timeout_s)
                job.ml = bool(results.get("ml"))
            except (ImageProblem, WorkerError) as e:
                log.warning("organizer failed (%s); keeping every photo in upload order", str(e)[:80])
                results = None
                job.ml = False
            finally:
                await asyncio.to_thread(self.ml.close)
            for s in sets:
                self.store.apply_organization(job, s, (results or {}).get("sets", {}).get(s.id) if results else None)
            log.info("job %s organised %d folder(s) in %.1fs (room model: %s)", job.id[:6], len(sets), time.time() - t0, job.ml)
        # edit the kept photos, main photo first
        queued: list[Item] = []
        with job.lock:
            for s in sorted(job.sets.values(), key=lambda s: natural_key(s.key)):
                ordered = [job.items[i] for i in s.order if i in job.items]
                queued += [i for i in ordered if i.status == "ready" and i.included]
            job.organizing = False
            job.bump()
        for it in queued:
            self.enqueue_process(job, it, mode)
        # photos that are set aside are edited quietly afterwards, so "Restore" is instant (see _preedit)
        with job.lock:
            aside = sorted((i for i in job.items.values() if i.status == "ready" and i.excluded and i.pre is None),
                           key=lambda i: (natural_key(i.group), natural_key(i.name), i.id))
        for it in aside:
            self._put(1, "preedit", job, it.id, mode)

    async def _edit(self, job: Job, item: Item, mode: str) -> dict:
        """Run the edit of one photo in the worker (group white balance first).  Raises ImageProblem / WorkerError."""
        with job.lock:
            group = [i.analysis for i in job.items.values() if i.group == item.group and i.analysis]
        group_wb = None
        if len(group) >= 2:
            try:
                group_wb = (await asyncio.to_thread(self.worker.call, "group", (group,), 60))["wb"]
            except Exception:
                group_wb = None
        return await asyncio.to_thread(
            self.worker.call, "process",
            (job.p_original(item.id), job.p_edited(item.id), job.p_preview, item.id, mode,
             group_wb, self.cfg.max_pixels, ingest.container_for(item.name), list(item.retouch),
             ENLARGE_TO if job.enlarge else 0),
            self.cfg.task_timeout_s)

    def adopt_preedit(self, job: Job, item: Item, mode: str) -> bool:
        """If a finished background edit of this photo is still valid, deliver it now (no waiting)."""
        with job.lock:
            p = item.pre
            if (item.status not in ("ready", "queued") or not p or p["mode"] != mode or p["enlarge"] != job.enlarge
                    or p["rt"] != len(item.retouch) or not os.path.exists(job.p_edited(item.id))):
                return False
            item.out_bytes, item.seconds, item.width, item.height = p["bytes"], p["sec"], p["w"], p["h"]
            item.mode, item.error, item.status = mode, None, "done"
            item.version += 1
            job.edit_version += 1
            job.downloaded_at = None
            job.bump()
            return True

    async def _preedit(self, job: Job, item: Item, mode: str) -> None:
        """Best effort, lowest priority: edit a photo that is set aside so that restoring it later costs nothing."""
        if (item.status != "ready" or not item.excluded or item.pre is not None
                or not os.path.exists(job.p_original(item.id))):
            return
        try:
            res = await self._edit(job, item, mode)
        except (ImageProblem, WorkerError):
            return
        with job.lock:
            if item.status in ("ready", "queued") and not job.deleting:
                item.pre = {"mode": mode, "enlarge": job.enlarge, "rt": len(item.retouch), "bytes": res["out_bytes"],
                            "sec": res["seconds"], "w": res["width"], "h": res["height"]}

    async def _process(self, job: Job, item: Item, mode: str) -> None:
        if item.status != "queued" or not os.path.exists(job.p_original(item.id)):
            return
        if self.adopt_preedit(job, item, mode):             # already edited quietly in the background
            return
        with job.lock:
            item.status = "processing"
            job.bump()
        try:
            res = await self._edit(job, item, mode)
        except (ImageProblem, WorkerError) as e:
            self._fail(job, item, str(e), drop_original=isinstance(e, ImageProblem))
            return
        with job.lock:
            item.out_bytes = res["out_bytes"]
            item.seconds = res["seconds"]
            item.width, item.height = res["width"], res["height"]
            item.status = "done"
            item.version += 1
            item.error = None
            item.pre = None
            job.edit_version += 1
            job.downloaded_at = None
            job.bump()
        log.info("job %s item %s done in %.1fs (%s)", job.id[:6], item.id, res["seconds"], mode)

    def _fail(self, job: Job, item: Item, message: str, drop_original: bool) -> None:
        with job.lock:
            item.status = "failed"
            item.error = message
            if item.set_id in job.sets:
                self.store._fix_order(job, job.sets[item.set_id])
            job.arr_version += 1
            job.bump()
        self.store.remove_item_files(job, item, original=drop_original)
        log.info("job %s item %s failed: %s", job.id[:6], item.id, message[:80])

    # -------------------------------------------------------------- user actions
    def start_job(self, job: Job, mode: str, smart: bool = True, enlarge: bool = False) -> int:
        """Fix the order (smart: also set same-shot copies aside), then edit every new photo that was kept."""
        mode = mode if mode in PRESETS else DEFAULT_MODE
        with job.lock:
            job.mode = mode
            todo = [i for i in job.items.values() if i.status in ("uploaded", "analyzing", "ready") and not i.excluded]
            if not todo or job.organizing:
                return 0 if not todo else len(todo)
            job.smart = bool(smart)
            job.enlarge = bool(enlarge)
            job.organizing = True
            job.bump()
        # analysis tasks of these photos are already ahead in the FIFO queue, so they finish before this runs
        self._put(0, "organize", job, None, mode)
        return len(todo)

    def reprocess(self, job: Job, item: Item, mode: str) -> None:
        self.enqueue_process(job, item, mode if mode in PRESETS else DEFAULT_MODE)
