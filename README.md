# Roomlit

Private web tool that enhances real-estate photos (Airbnb listings) with **deterministic, non-generative**
image processing. Upload photos, folders or ZIPs straight from an external drive, pick a mode, review
before/after, download one organised ZIP. Nothing is stored permanently.

* Python · FastAPI · OpenCV · Pillow · NumPy · plain HTML/CSS/JS (English + Arabic/RTL)
* No paid APIs, no generative models. Every pixel in the output derives from the same pixel in the input.

## What the editor does (and never does)

Per photo it measures the image and moves it toward the mode's target **within hard limits**:

| Step | How |
|---|---|
| White balance | illuminant estimated from the brightest near-neutral surfaces; correction is partial and capped (±5 / 8 / 10 %) |
| Exposure + shadows | smooth, edge-aware gain map (guided filter) so local detail is preserved; true blacks are not lifted |
| Windows / lamps | exposure change fades out in bright areas, soft highlight shoulder; never brightens clipped windows |
| Whites (bedding, walls) | faint tints on near-white surfaces are neutralised (only surfaces that are already almost white) |
| Blue sofas | lifted in brightness with **hue and saturation held constant** |
| Noise | edge-preserving luma + chroma denoise, strength driven by the measured noise of that photo |
| Sharpness / clarity | luminance-only, with a noise floor, weaker in lifted shadows |

Never: crop, rotate, resize, add/remove/replace objects, recolour furniture, hide defects, generate or
“reconstruct” detail, or apply HDR-style tone mapping. Output has the **same pixel dimensions**; EXIF
(incl. orientation) and the ICC profile are carried over; JPEG quality 94.

Modes: **Natural** (subtle), **Premium Airbnb** (default), **Bright & Clean**.
Photos in the **same folder** are treated as one apartment: they share a brightness target and a
shared colour-cast fallback so they look consistent.

## Folder mapping

```
Photos Al Khuzama/1/a.jpg      ->  Photos Al Khuzama - Edited/1/Edited - Airbnb/a.jpg
Photos Al Khuzama/02/b.jpg     ->  Photos Al Khuzama - Edited/02/Edited - Airbnb/b.jpg
```
Original names and folder hierarchy are kept; duplicate names get ` (2)`, ` (3)`; unsupported files are
ignored (and counted). HEIC is delivered as JPG.

## Privacy and safety model

* Single login (`APP_USERNAME` / `APP_PASSWORD`), signed HttpOnly cookie, login lockout after repeated failures,
  CSRF header + Origin check, strict CSP and security headers. Photos are never served without a session.
* Each job lives in its own random-named temp folder; uploaded files are stored under opaque names (client
  paths are only metadata), so path traversal cannot touch the filesystem. ZIP extraction rejects
  `..`/absolute paths, symlinks, encrypted and bomb-shaped entries and enforces file-count/size limits.
* State is in memory only; every restart wipes all photos. Jobs are deleted by: the **Delete** button, the
  prompt after a ZIP download, expiry (`JOB_TTL_MINUTES`, default 120; 30 min after a completed ZIP download),
  and immediately for jobs that failed completely.
* Image bytes and filenames are not logged.
* Your originals are only ever *read*. Note a browser upload may use temporary space on your Mac.

## Limits (all configurable, see below)

80 MB per photo, 40 megapixels per photo (larger photos are rejected with a clear message — never silently
downscaled), 400 photos / 2000 MB per job, 6 open jobs. Photos are processed one at a time in a separate
worker process (memory use is bounded by strips, ~3 bytes per pixel + a small working set); if a photo
crashes or times out, only that photo fails.

## Configuration (environment variables)

`APP_PASSWORD` (required) · `APP_USERNAME` (default `admin`) · `SESSION_SECRET` · `SESSION_HOURS`=12 ·
`DATA_DIR`=/tmp/roomlit · `JOB_TTL_MINUTES`=120 · `DOWNLOADED_TTL_MINUTES`=30 · `FAILED_TTL_MINUTES`=10 ·
`MAX_FILE_MB`=80 · `MAX_ZIP_MB`=1500 · `MAX_JOB_MB`=2000 · `MAX_FILES_PER_JOB`=400 · `MAX_JOBS`=6 ·
`MAX_MEGAPIXELS`=40 · `MIN_FREE_DISK_MB`=300 · `CV_THREADS`=1 · `WORKER_RECYCLE`=12 · `TASK_TIMEOUT_S`=420

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
APP_ENV=dev APP_PASSWORD=dev-password .venv/bin/python -m uvicorn app.main:app --port 8765
.venv/bin/python -m pytest tests          # 30+ tests: engine fidelity, ZIP/path safety, API security, cleanup
```
`tests/fetch_samples.py` downloads openly licensed (CC0/CC BY) interior photos for local experiments.

## Deploy (Render)

`render.yaml` describes one web service (Starter, 1 instance — keep it at 1: job state is in memory).
Set `APP_PASSWORD` in the dashboard. Health check: `/healthz`.

## Changing the product name

The name appears in `app/static/index.html` (`<title>`, header) and `app/main.py`.
