"""Reading and writing photos without changing their pixels' geometry.

JPEGs are decoded straight to a single uint8 BGR array (3 bytes/pixel) so large
photos fit in a small server.  EXIF (including orientation) and the ICC profile
are carried over untouched, so the edited file opens upright and in the same
colour space as the original, with exactly the same pixel dimensions.
"""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageFile

try:  # iPhone photos
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_OK = True
except Exception:  # pragma: no cover - optional dependency
    HEIC_OK = False

ImageFile.LOAD_TRUNCATED_IMAGES = False

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif"}
JPEG_QUALITY = 94


class ImageError(Exception):
    """A user-facing problem with one photo."""


@dataclass
class Meta:
    fmt: str                       # PIL format name of the *source*: JPEG, PNG, WEBP, TIFF, HEIF
    width: int
    height: int
    orientation: int = 1
    exif: bytes | None = None
    icc: bytes | None = None
    out_ext: str = ".jpg"


def set_pixel_limit(max_pixels: int) -> None:
    Image.MAX_IMAGE_PIXELS = max_pixels


def _clean_exif(im: Image.Image) -> bytes | None:
    """EXIF bytes without the embedded (stale, un-edited) thumbnail."""
    try:
        ex = im.getexif()
        if not len(ex):
            return None
        data = ex.tobytes()
        return b"Exif\x00\x00" + data if not data.startswith(b"Exif") else data
    except Exception:
        raw = im.info.get("exif")
        return raw if isinstance(raw, (bytes, bytearray)) else None


def inspect(path: str, max_pixels: int) -> Meta:
    """Header-only validation.  Raises ImageError with a message suitable for the user."""
    try:
        with Image.open(path) as im:
            fmt = (im.format or "").upper()
            w, h = im.size
            if fmt not in {"JPEG", "PNG", "WEBP", "TIFF", "MPO", "HEIF"}:
                raise ImageError("Not a supported photo format")
            if w * h > max_pixels:
                raise ImageError(
                    f"Image is {w * h / 1e6:.0f} megapixels; the limit is {max_pixels / 1e6:.0f}. "
                    "It was not downscaled - please edit it separately."
                )
            if w < 16 or h < 16:
                raise ImageError("Image is too small")
            if fmt == "MPO":
                fmt = "JPEG"
            orientation = int(im.getexif().get(0x0112, 1) or 1)
            ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "TIFF": ".tif", "HEIF": ".heic"}[fmt]
            return Meta(
                fmt=fmt, width=w, height=h, orientation=orientation,
                exif=_clean_exif(im), icc=im.info.get("icc_profile"), out_ext=ext,
            )
    except ImageError:
        raise
    except Image.DecompressionBombError:
        raise ImageError("Image is too large to process safely")
    except Exception:
        raise ImageError("File is not a readable image")


def load_bgr(path: str, meta: Meta) -> np.ndarray:
    """Decode to a C-contiguous uint8 BGR array with the *stored* pixel layout (no rotation)."""
    img = None
    if meta.fmt == "JPEG":
        buf = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        del buf
        if img is not None and img.shape[:2] != (meta.height, meta.width):
            img = None
    if img is None:
        try:
            with Image.open(path) as im:
                if meta.fmt in ("HEIF",) or im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                elif im.mode == "L":
                    im = im.convert("RGB")
                rgb = np.asarray(im)
                img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:
            raise ImageError("File is not a readable image")
    if img.shape[:2] != (meta.height, meta.width):
        # HEIC decoders may pre-rotate; trust the decoded pixels
        meta.height, meta.width = img.shape[:2]
        meta.orientation = 1
    return np.ascontiguousarray(img)


def _apply_orientation(img: np.ndarray, orientation: int) -> np.ndarray:
    """Return a display-oriented *view/copy* for previews only."""
    if orientation == 2:
        return cv2.flip(img, 1)
    if orientation == 3:
        return cv2.rotate(img, cv2.ROTATE_180)
    if orientation == 4:
        return cv2.flip(img, 0)
    if orientation == 5:
        return cv2.flip(cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE), 1)
    if orientation == 6:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if orientation == 7:
        return cv2.flip(cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE), 1)
    if orientation == 8:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def make_preview(img: np.ndarray, orientation: int, long_edge: int) -> np.ndarray:
    h, w = img.shape[:2]
    s = long_edge / max(h, w)
    small = img if s >= 1.0 else cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
    return _apply_orientation(small, orientation)


def save_preview(path: str, img: np.ndarray, quality: int = 85) -> None:
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ImageError("Could not create preview")
    with open(path, "wb") as f:
        f.write(enc.tobytes())


# ---------------------------------------------------------------- JPEG metadata splice
def _app_segment(marker: int, payload: bytes) -> bytes:
    return struct.pack(">BBH", 0xFF, marker, len(payload) + 2) + payload


def _splice_jpeg(data: bytes, exif: bytes | None, icc: bytes | None) -> bytes:
    if not data.startswith(b"\xff\xd8"):
        return data
    segs = b""
    if exif and len(exif) + 2 <= 0xFFFF:
        segs += _app_segment(0xE1, exif)
    if icc:
        chunk = 65000                   # APP2 payload limit is 65533 incl. the 14-byte ICC header
        parts = [icc[i:i + chunk] for i in range(0, len(icc), chunk)]
        for i, part in enumerate(parts, 1):
            segs += _app_segment(0xE2, b"ICC_PROFILE\x00" + bytes([i, len(parts)]) + part)
    if not segs:
        return data
    pos = 2
    # keep a leading JFIF APP0 first, as PIL does
    if data[2:4] == b"\xff\xe0":
        (ln,) = struct.unpack(">H", data[4:6])
        pos = 4 + ln
    return data[:pos] + segs + data[pos:]


def enlarge(img: np.ndarray, target_long: int, max_scale: float = 2.5) -> np.ndarray:
    """Photos smaller than `target_long` (long edge) are enlarged with the same proportions; larger ones are returned as is.

    Lanczos interpolation, then a thresholded unsharp mask that restores the edge crispness interpolation takes away
    without boosting grain.  Nothing is invented: it is the same picture on a bigger canvas."""
    h, w = img.shape[:2]
    if target_long <= 0 or max(h, w) >= target_long:
        return img
    s = min(max_scale, target_long / max(h, w))
    out = cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(out, (0, 0), 0.8 * s ** 0.5)
    d = out.astype(np.int16) - blur.astype(np.int16)
    d[np.abs(d) < 3] = 0                                   # below the noise floor: leave alone
    return np.clip(out.astype(np.int16) + (0.6 * d).astype(np.int16), 0, 255).astype(np.uint8)


def exif_with_size(exif: bytes | None, w: int, h: int) -> bytes | None:
    """EXIF whose pixel-dimension tags match the (enlarged) picture; unchanged if it cannot be rewritten."""
    if not exif:
        return exif
    try:
        ex = Image.Exif()
        ex.load(exif)
        sub = ex.get_ifd(0x8769)
        for tag, val in ((0xA002, w), (0xA003, h)):
            if tag in sub:
                sub[tag] = val
        for tag, val in ((0x0100, w), (0x0101, h)):
            if tag in ex:
                ex[tag] = val
        return b"Exif\x00\x00" + ex.tobytes()
    except Exception:
        return exif


def encode(img: np.ndarray, meta: Meta) -> bytes:
    """Encode the edited pixels in the right container, carrying EXIF + ICC."""
    if meta.out_ext == ".jpg":
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
        if not ok:
            raise ImageError("Could not encode the edited photo")
        return _splice_jpeg(enc.tobytes(), meta.exif, meta.icc)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    buf = io.BytesIO()
    kw: dict = {}
    if meta.icc:
        kw["icc_profile"] = meta.icc
    if meta.out_ext == ".png":
        pil.save(buf, "PNG", **kw)
    elif meta.out_ext == ".heic":
        if not HEIC_OK:
            raise ImageError("HEIC files cannot be written on this server; convert the photo to JPG first")
        if meta.exif:
            kw["exif"] = meta.exif
        pil.save(buf, "HEIF", quality=90, **kw)
    elif meta.out_ext == ".webp":
        pil.save(buf, "WEBP", quality=95, method=4, **kw)
    else:
        pil.save(buf, "TIFF", compression="tiff_lzw", **kw)
    return buf.getvalue()
