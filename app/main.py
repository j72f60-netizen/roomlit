"""Roomlit - FastAPI application."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

import threading

from . import config, ingest, modelfetch
from .engine.presets import DEFAULT_MODE, PRESETS
from .engine.retouch_ops import BadStrokes, clean_ops
from .runner import Dispatcher
from .security import COOKIE, Auth, SecurityMiddleware, client_ip
from .store import DEFAULT_SUFFIX, Item, Job, JobError, JobStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("roomlit")

cfg = config.load()
store = JobStore(cfg)
auth = Auth(cfg)
dispatcher = Dispatcher(cfg, store)
STATIC = os.path.join(os.path.dirname(__file__), "static")


async def _janitor() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            for job in store.expired():
                log.info("job %s expired", job.id[:6])
                await asyncio.to_thread(store.delete, job)
        except Exception:
            log.exception("janitor error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not modelfetch.present(cfg.model_dir):            # fetch the room model in the background; editing never waits for it
        threading.Thread(target=modelfetch.fetch, args=(cfg.model_dir,), daemon=True, name="model-fetch").start()
    dispatcher.start()
    jan = asyncio.create_task(_janitor())
    log.info("started: ttl=%dmin max_file=%dMB max_job=%dMB max_files=%d", cfg.job_ttl_minutes,
             cfg.max_file_mb, cfg.max_job_mb, cfg.max_files_per_job)
    yield
    jan.cancel()
    await dispatcher.stop()
    shutil.rmtree(cfg.jobs_dir, ignore_errors=True)


app = FastAPI(title="Roomlit", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityMiddleware, cfg=cfg)


@app.exception_handler(JobError)
async def job_error_handler(request: Request, exc: JobError):
    return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)


# ------------------------------------------------------------------ auth
def current_user(request: Request) -> str:
    user = auth.read(request.cookies.get(COOKIE))
    if not user:
        raise JobError(401, "unauthorized", "Please sign in.")
    return user


@app.post("/api/login")
async def login(request: Request, response: Response):
    ip = client_ip(request)
    left = auth.locked_for(ip)
    if left:
        return JSONResponse({"error": "locked", "message": "Too many attempts.", "retry_after": left}, status_code=429)
    try:
        body = await request.json()
        username, password = str(body.get("username", "")), str(body.get("password", ""))
    except Exception:
        raise JobError(400, "bad_request", "Invalid request")
    if not auth.check(username, password):
        auth.record_failure(ip)
        await asyncio.sleep(0.7)
        raise JobError(401, "bad_credentials", "Wrong username or password.")
    auth.record_success(ip)
    resp = JSONResponse({"ok": True, "user": cfg.username})
    resp.set_cookie(COOKIE, auth.issue(cfg.username), max_age=cfg.session_hours * 3600, httponly=True,
                    secure=not cfg.dev, samesite="lax", path="/")
    return resp


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/api/me")
async def me(user: str = Depends(current_user)):
    return {"user": user}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config(user: str = Depends(current_user)):
    return {
        "modes": [DEFAULT_MODE] + [m for m in PRESETS if m != DEFAULT_MODE], "default_mode": DEFAULT_MODE,
        "exts": sorted(ingest.IMAGE_EXTS), "max_file_mb": cfg.max_file_mb, "max_zip_mb": cfg.max_zip_mb,
        "max_job_mb": cfg.max_job_mb, "max_files": cfg.max_files_per_job, "max_megapixels": cfg.max_megapixels,
        "job_ttl_minutes": cfg.job_ttl_minutes, "downloaded_ttl_minutes": cfg.downloaded_ttl_minutes,
        "room_model": modelfetch.present(cfg.model_dir),
    }


# ------------------------------------------------------------------ helpers
def _rss(pid: int | str, key: str = "VmRSS") -> float | None:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith(key + ":"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


@app.get("/api/diag")
async def diag(user: str = Depends(current_user)):
    du = shutil.disk_usage(cfg.data_dir)
    jobs_bytes = 0
    n_files = 0
    for dp, _, fs in os.walk(cfg.jobs_dir):
        n_files += len(fs)
        for f in fs:
            try:
                jobs_bytes += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    wpid = dispatcher.worker.pid
    return {
        "jobs": len(store.jobs), "files_on_disk": n_files, "job_bytes_on_disk": jobs_bytes,
        "disk_free_mb": round(du.free / 1e6), "queue": dispatcher.pending,
        "web_rss_mb": _rss("self"), "web_peak_rss_mb": _rss("self", "VmHWM"),
        "worker_rss_mb": _rss(wpid) if wpid else None, "worker_peak_mb": dispatcher.worker.peak_mb,
        "organizer_peak_mb": dispatcher.ml.peak_mb,
        "uptime_s": int(time.time() - START),
    }


START = time.time()


def _job(job_id: str, user: str) -> Job:
    return store.get(job_id, user)


def _item(job: Job, item_id: int) -> Item:
    it = job.items.get(item_id)
    if it is None:
        raise JobError(404, "item_not_found", "Photo not found")
    return it


def _mode(v) -> str:
    return v if isinstance(v, str) and v in PRESETS else DEFAULT_MODE


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ------------------------------------------------------------------ jobs
@app.post("/api/jobs")
async def create_job(request: Request, user: str = Depends(current_user)):
    body = await _json(request)
    job = store.create(user, _mode(body.get("mode")))
    log.info("job %s created", job.id[:6])
    return store.public(job)


@app.get("/api/jobs")
async def list_jobs(user: str = Depends(current_user)):
    return {"jobs": [store.summary(j) for j in store.list_for(user)]}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, since: int = Query(0), user: str = Depends(current_user)):
    job = _job(job_id, user)
    if since and since == job.rev:
        return {"id": job.id, "rev": job.rev, "unchanged": True, "expires_in": store.expires_in(job)}
    return store.public(job)


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, user: str = Depends(current_user)):
    job = _job(job_id, user)
    await asyncio.to_thread(store.delete, job)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/files")
async def upload(job_id: str, request: Request, path: str = Query(..., max_length=2000),
                 user: str = Depends(current_user)):
    """One photo (or one ZIP) per request, as a raw body streamed straight to disk."""
    job = _job(job_id, user)
    try:
        parts = ingest.split_rel(path)
    except ingest.UnsafePath:
        raise JobError(400, "bad_path", "Invalid file path")
    kind = ingest.kind_of(parts)
    if kind == "junk":
        return {"accepted": 0, "ignored": 0}
    if kind == "unsupported":
        with job.lock:
            job.ignored["unsupported"] = job.ignored.get("unsupported", 0) + 1
            job.bump()
        return {"accepted": 0, "ignored": 1, "reason": "unsupported"}

    limit = (cfg.max_zip_mb if kind == "zip" else cfg.max_file_mb) * 1_000_000
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit:
        raise JobError(413, "file_too_large", f"This file is larger than the {limit // 1_000_000} MB limit.")
    store._check_disk()
    job.touch()

    tmp = store.new_tmp_path(job)
    size = 0
    digest = hashlib.sha256()
    try:
        with open(tmp, "wb") as f:
            buf = bytearray()
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise JobError(413, "file_too_large", f"This file is larger than the {limit // 1_000_000} MB limit.")
                digest.update(chunk)
                buf += chunk
                if len(buf) >= (1 << 20):
                    await run_in_threadpool(f.write, bytes(buf))
                    buf.clear()
            if buf:
                await run_in_threadpool(f.write, bytes(buf))
        if size == 0:
            raise JobError(400, "empty_file", "The file is empty.")
    except BaseException:
        ingest._rm(tmp)
        raise

    if kind == "zip":
        stem = os.path.splitext(parts[-1])[0]
        try:
            entries, ignored = await run_in_threadpool(
                ingest.extract_zip, tmp, stem, lambda: store.new_tmp_path(job),
                max_files=cfg.max_files_per_job - len(job.items),
                max_file_bytes=cfg.max_file_mb * 1_000_000,
                max_total_bytes=max(0, cfg.max_job_mb * 1_000_000 - job.bytes_total))
        except ingest.ZipRejected as e:
            raise JobError(400, "zip_rejected", str(e))
        finally:
            ingest._rm(tmp)
        accepted = same = done = 0
        try:
            for ent in entries:
                it = store.add_item(job, ent.parts, ent.tmp_path, ent.size, ent.sha)
                done += 1
                if it is None:
                    same += 1
                    continue
                dispatcher.enqueue_analyze(job, it)
                accepted += 1
        except JobError:
            for ent in entries[done:]:
                ingest._rm(ent.tmp_path)
            raise
        with job.lock:
            for k, v in ignored.items():
                if v:
                    job.ignored[k] = job.ignored.get(k, 0) + v
            job.bump()
        return {"accepted": accepted, "ignored": sum(ignored.values()), "duplicate": same}

    item = store.add_item(job, parts, tmp, size, digest.hexdigest())
    if item is None:                      # the very same file again (retry / folder added twice): never a second photo
        return {"accepted": 0, "ignored": 0, "duplicate": 1}
    dispatcher.enqueue_analyze(job, item)
    return {"accepted": 1, "ignored": 0, "id": item.id}


@app.post("/api/jobs/{job_id}/start")
async def start_job(job_id: str, request: Request, user: str = Depends(current_user)):
    job = _job(job_id, user)
    body = await _json(request)
    job.touch()
    n = dispatcher.start_job(job, _mode(body.get("mode", job.mode)), body.get("smart") is not False, body.get("enlarge") is True)
    if not n:
        raise JobError(409, "nothing_to_process", "There are no new photos to process.")
    return {"queued": n}


@app.post("/api/jobs/{job_id}/reprocess")
async def reprocess_all(job_id: str, request: Request, user: str = Depends(current_user)):
    job = _job(job_id, user)
    mode = _mode((await _json(request)).get("mode"))
    job.touch()
    n = 0
    for it in list(job.items.values()):
        if it.status in ("done", "failed") and os.path.exists(job.p_original(it.id)):
            dispatcher.reprocess(job, it, mode)
            n += 1
    job.mode = mode
    if not n:
        raise JobError(409, "nothing_to_process", "There are no photos to reprocess.")
    return {"queued": n}


@app.post("/api/jobs/{job_id}/items/{item_id}/reprocess")
async def reprocess_one(job_id: str, item_id: int, request: Request, user: str = Depends(current_user)):
    job = _job(job_id, user)
    it = _item(job, item_id)
    mode = _mode((await _json(request)).get("mode"))
    if it.status not in ("done", "failed") or not os.path.exists(job.p_original(it.id)):
        raise JobError(409, "not_reprocessable", "This photo cannot be reprocessed right now.")
    job.touch()
    dispatcher.reprocess(job, it, mode)
    return {"ok": True}


def _preview_response(job: Job, item: Item, kind: str) -> FileResponse:
    if kind not in ("before", "after", "thumb"):
        raise JobError(404, "not_found")
    p = os.path.join(job.p_preview, f"{item.id}_{kind}.jpg")
    if not os.path.exists(p):
        raise JobError(404, "preview_not_ready", "Preview is not ready yet")
    job.touch()
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/jobs/{job_id}/items/{item_id}/preview/{kind}")
async def preview(job_id: str, item_id: int, kind: str, user: str = Depends(current_user)):
    job = _job(job_id, user)
    return _preview_response(job, _item(job, item_id), kind)


_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
          ".tif": "image/tiff", ".tiff": "image/tiff"}


@app.get("/api/jobs/{job_id}/items/{item_id}/download")
async def download_one(job_id: str, item_id: int, user: str = Depends(current_user)):
    job = _job(job_id, user)
    it = _item(job, item_id)
    p = job.p_edited(it.id)
    if it.status != "done" or not os.path.exists(p):
        raise JobError(409, "not_ready", "This photo has not been edited yet.")
    job.touch()
    name = it.out_rel.rsplit("/", 1)[-1]
    return FileResponse(p, filename=name, media_type=_MEDIA.get(os.path.splitext(name)[1].lower(), "application/octet-stream"),
                        headers={"Cache-Control": "private, no-store"})


@app.get("/api/jobs/{job_id}/download.zip")
async def download_zip(job_id: str, numbering: int = Query(1), suffix: str = Query(DEFAULT_SUFFIX, max_length=80),
                       user: str = Depends(current_user)):
    """`<folder name> <suffix>.zip`: the folder you sent + "after editing", same sub-folders, photos in final order."""
    job = _job(job_id, user)
    path = await run_in_threadpool(store.build_zip, job, bool(numbering), suffix)
    job.touch()

    def mark() -> None:
        job.downloaded_at = time.time()
        job.bump()

    return FileResponse(path, filename=store.zip_name(job, suffix), media_type="application/zip",
                        headers={"Cache-Control": "private, no-store"}, background=BackgroundTask(mark))


@app.get("/api/jobs/{job_id}/log.csv")
async def download_log(job_id: str, numbering: int = Query(1), suffix: str = Query(DEFAULT_SUFFIX, max_length=80),
                       user: str = Depends(current_user)):
    """Download log: where every original photo went (final name, position, room, excluded and why)."""
    job = _job(job_id, user)
    data = await run_in_threadpool(store.log_for, job, bool(numbering), suffix)
    job.touch()
    return Response(data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=\"Roomlit log.csv\"", "Cache-Control": "private, no-store"})


# ------------------------------------------------------------------ arrange: exclude / restore / order / main / room
def _set(job: Job, set_id: int):
    s = job.sets.get(set_id)
    if s is None:
        raise JobError(404, "set_not_found", "Folder not found")
    return s


def _edit_if_needed(job: Job, it: Item) -> None:
    """A photo that was excluded before it was edited has to be edited when it comes back."""
    if it.status == "ready" and job.sets[it.set_id].organized and it.included:
        dispatcher.enqueue_process(job, it, job.mode)


@app.post("/api/jobs/{job_id}/items/{item_id}/exclude")
async def exclude_item(job_id: str, item_id: int, user: str = Depends(current_user)):
    job = _job(job_id, user)
    it = _item(job, item_id)
    job.touch()
    for promoted in store.set_exclude(job, it):          # a twin takes over so the angle is not lost
        _edit_if_needed(job, promoted)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/items/{item_id}/restore")
async def restore_item(job_id: str, item_id: int, user: str = Depends(current_user)):
    job = _job(job_id, user)
    it = _item(job, item_id)
    if it.status == "failed":
        raise JobError(409, "failed_item", "This photo could not be processed.")
    job.touch()
    store.set_restore(job, it)
    _edit_if_needed(job, it)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/items/{item_id}/main")
async def make_main(job_id: str, item_id: int, user: str = Depends(current_user)):
    job = _job(job_id, user)
    job.touch()
    store.make_main(job, _item(job, item_id))
    return {"ok": True}


@app.get("/api/jobs/{job_id}/items/{item_id}/retouch")
async def get_retouch(job_id: str, item_id: int, user: str = Depends(current_user)):
    job = _job(job_id, user)
    return {"ops": list(_item(job, item_id).retouch)}


@app.post("/api/jobs/{job_id}/items/{item_id}/retouch")
async def set_retouch(job_id: str, item_id: int, request: Request, user: str = Depends(current_user)):
    """Replace the user's touch-up strokes for one photo and edit it again with them ([] clears them)."""
    job = _job(job_id, user)
    it = _item(job, item_id)
    try:
        ops = clean_ops((await _json(request)).get("ops"))
    except BadStrokes as e:
        raise JobError(400, "bad_strokes", str(e))
    if it.status not in ("ready", "done", "failed") or not os.path.exists(job.p_original(it.id)):
        raise JobError(409, "not_retouchable", "This photo cannot be retouched right now.")
    job.touch()
    store.set_retouch(job, it, ops)
    again = it.status in ("done", "failed")          # a photo still waiting (e.g. excluded) just keeps the strokes for later
    if again:
        dispatcher.reprocess(job, it, it.mode or job.mode)
    return {"ok": True, "queued": again}


@app.post("/api/jobs/{job_id}/items/{item_id}/room")
async def set_room(job_id: str, item_id: int, request: Request, user: str = Depends(current_user)):
    job = _job(job_id, user)
    job.touch()
    store.set_room(job, _item(job, item_id), str((await _json(request)).get("room", "")))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/sets/{set_id}/order")
async def set_order(job_id: str, set_id: int, request: Request, user: str = Depends(current_user)):
    job = _job(job_id, user)
    order = (await _json(request)).get("order")
    if not isinstance(order, list) or not all(isinstance(i, int) for i in order):
        raise JobError(400, "bad_request", "Invalid order")
    job.touch()
    store.set_order(job, _set(job, set_id), order)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/sets/{set_id}/reset-order")
async def reset_order(job_id: str, set_id: int, user: str = Depends(current_user)):
    job = _job(job_id, user)
    job.touch()
    store.reset_order(job, _set(job, set_id))
    return {"ok": True}


# ------------------------------------------------------------------ static
def _asset_version() -> str:
    """Changes whenever a static file changes, so a browser never mixes a new page with old CSS / JS."""
    try:
        return str(int(max(os.path.getmtime(os.path.join(STATIC, f)) for f in os.listdir(STATIC))))
    except OSError:
        return "0"


@app.get("/", include_in_schema=False)
async def index():
    with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
        html = f.read()
    v = _asset_version()
    for asset in ("app.css", "app.js"):
        html = html.replace(f'/static/{asset}"', f'/static/{asset}?v={v}"')
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-store"})


class _RevalidatedStatic(StaticFiles):
    """Static files are re-checked (ETag) on every load instead of being cached heuristically for hours."""
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", _RevalidatedStatic(directory=STATIC), name="static")

# Development only: lets browser tests pull sample photos from the same origin (never active in production).
if cfg.dev and os.environ.get("DEV_SAMPLES_DIR"):
    app.mount("/dev-samples", StaticFiles(directory=os.environ["DEV_SAMPLES_DIR"]), name="dev-samples")
