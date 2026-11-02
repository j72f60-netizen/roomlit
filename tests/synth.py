"""Deterministic synthetic 'apartment' photos with known ground truth (blue sofa, white bedding, window)."""
import io
import numpy as np
import cv2
from PIL import Image, ImageCms

SOFA = (slice(330, 470), slice(60, 330))       # y, x
BED = (slice(300, 420), slice(380, 640))
WINDOW = (slice(60, 220), slice(430, 600))


def scene(w=800, h=560, seed=7, dark=0.55, noise=2.0):
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.50, 0.55, 0.60)                                   # BGR warm-ish wall
    img[int(h * 0.75):] = (0.25, 0.32, 0.45)                      # wooden floor
    img[SOFA] = (0.52, 0.30, 0.16)                                # blue sofa  (BGR)
    img[BED] = (0.78, 0.84, 0.88)                                 # white bedding with a faint warm cast
    img[WINDOW] = (1.0, 1.0, 1.0)                                 # blown window
    img[10:50, 20:120] = (0.04, 0.05, 0.06)                       # dark corner
    img = img * dark
    img += rng.normal(0, noise / 255, img.shape).astype(np.float32)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def srgb_icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def save_jpeg(path, bgr, orientation=None, icc=False, quality=95):
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    kw = {}
    if orientation:
        ex = Image.Exif(); ex[0x0112] = orientation; ex[0x010F] = "TestCam"; kw["exif"] = ex
    if icc:
        kw["icc_profile"] = srgb_icc()
    im.save(path, "JPEG", quality=quality, **kw)


def hsv(bgr_region):
    return cv2.cvtColor(bgr_region.astype(np.float32) / 255.0, cv2.COLOR_BGR2HSV)
