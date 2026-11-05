# Roomlit

Private web tool that enhances real-estate photos (Airbnb listings) with **deterministic, non-generative**
image processing. Upload photos, folders or ZIPs straight from an external drive, pick a mode, review
before/after, download one organised ZIP. Nothing is stored permanently.

* Python · FastAPI · OpenCV · Pillow · NumPy · plain HTML/CSS/JS (English + Arabic/RTL)
* No paid APIs, no generative models. Every pixel in the output derives from the same pixel in the input, except where you
  paint a touch-up yourself (see Retouch).

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

Modes: **Pro Listing** (default: the bright, airy professional-listing look - tuned against a reference photographer edit of
a real living room, matching its tonal distribution within a couple of levels: lifted shadows, a soft highlight shoulder,
clean warm-white walls, fresh white bedding, brighter blue furniture in the same blue, one consistent look across a folder),
**Premium Airbnb** (the earlier, more conservative default), **Natural** (subtle) and **Bright & Clean**.

**Enhance resolution** (page option, on by default): photos smaller than 2048 px on the long side are enlarged to 2048 px (never
more than 2.5x) with the same proportions - Lanczos plus a thresholded unsharp pass that restores edge crispness without
boosting grain. Larger photos keep their size. Nothing is invented: it is the same picture on a bigger canvas.
Photos in the **same folder** are one apartment: they share a brightness target and a colour-cast fallback so they look consistent.

## Plain mode: one photo in, one photo out (untick "Smart organise")

Nothing is removed, moved or renamed:

* every uploaded file produces **exactly one** edited file (similar-looking and even byte-identical photos stay separate);
* the order is the file-manager order of the names, folder by folder (`IMG_2` before `IMG_10`, `IMG_1.jpg` before
  `IMG_1 copy.jpg`), whatever order the files arrived in;
* with "Number the photos" unticked the edited file keeps its **exact name and extension**, written in the format that
  name promises (`.jpg`/`.jpeg` JPEG, `.png` PNG, `.webp` WebP, `.tif`/`.tiff` TIFF, `.heic`/`.heif` HEIC);
* the same file arriving twice (retried upload, folder added again) is ignored, never duplicated;
* only two *different* photos with the very same path cannot both keep the name; the second gets ` (2)` and is flagged.

## Smart organise (the default)

Per **apartment** (= the folder that directly contains the photos; folders are never merged):

* **Duplicates**: the same shot is recognised by geometry (ORB features + RANSAC), not by name, size or brightness:
  copies, resized/recompressed versions, relit versions and tiny handheld shifts. The sharpest, best-exposed, highest
  resolution copy is kept. Different angles of the same room are **never** duplicates. Borderline pairs are kept and
  tagged "Similar". Excluded photos are shown in their own section and can be **restored** (a restored photo is edited
  on the spot and placed next to its twin). Nothing is deleted before the job is deleted after download.
* **Room type + order**: a small local model (OpenAI CLIP ViT-B/32, MIT licence, int8 ONNX, ~89 MB, runs on CPU; no paid
  or external AI) suggests the room type with a confidence. Weak guesses are marked *unsure* and are editable.
  Order: main photo -> living room -> bedrooms -> kitchen -> bathrooms -> dining / balcony / amenities -> views,
  entrance, exterior, parking. Different angles of one room are spread out; rooms that do not exist are never invented.
* **Control**: drag and drop (or the arrow buttons) to reorder, "Make main photo", Exclude / Restore, correct a room label,
  "Suggested order" to start over. The header shows original / final / excluded counts.

## Retouch (you paint, the bot fixes only that spot)

Open a photo, press **Retouch**, paint over the spot and press *Apply and re-edit*; compare with Before / After.

* **Remove object**: the painted area is filled from the pixels around it (diffusion inpainting + the surrounding grain), with
  no AI model. Works best on thin or small things on plain surfaces (broom handle, cable, socket, a mark); anything
  behind a big object, or a busy background, can smudge, so paint tightly. Nothing outside the stroke changes.
* **Smooth fabric**: softens low-contrast creases on sheets and curtains (luma only, edges and grain kept). It softens
  creases, it cannot iron a heavily rumpled duvet.
* Strokes are saved per photo, survive "re-edit", and can be cleared. Excluded photos keep them for when they are restored.
* Same angle shot many times: Smart organise keeps the **best two** photos of one viewpoint and sets the rest aside
  (restorable); different angles are never capped.

## Download

`<folder name you sent> بعد التعديل.zip` ("after editing", editable or removable in the page) -> the same folder name +
suffix, your own sub-folders, and the photos in their final order as `NN - <original file name>` (so Airbnb, Booking,
Gathern and the like keep the order when you drag the files in; untick "Number the photos" for the exact original names).
Duplicates set aside by Smart organise are not in the ZIP; `Download log` is a separate CSV (original name, final name
and path, position, room type, main photo, excluded + why). No "Edited" / "Airbnb" words are added unless you type them
as the suffix. The ZIP is refused while photos are still being edited, so it can never be a partial result by accident.

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
`MAX_MEGAPIXELS`=40 · `MIN_FREE_DISK_MB`=300 · `CV_THREADS`=1 · `WORKER_RECYCLE`=12 · `TASK_TIMEOUT_S`=420 · `ORGANIZE_TIMEOUT_S`=900 · `MODEL_DIR`

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
APP_ENV=dev APP_PASSWORD=dev-password .venv/bin/python -m uvicorn app.main:app --port 8765
.venv/bin/python -m pytest tests          # 30+ tests: engine fidelity, ZIP/path safety, API security, cleanup
```
`tests/fetch_samples.py` downloads openly licensed (CC0/CC BY) interior photos for local experiments.

## Deploy (Render)

`render.yaml` describes one web service (Starter, 1 instance - keep it at 1: job state is in memory). The room model
is downloaded (SHA-256 checked) in the background at first start if it is not already there.
Set `APP_PASSWORD` in the dashboard. Health check: `/healthz`.

## Changing the product name

The name appears in `app/static/index.html` (`<title>`, header) and `app/main.py`.
