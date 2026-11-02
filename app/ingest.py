"""Turning whatever the browser sends into safe, normalised photo entries.

Nothing in here ever uses a client-supplied name as a filesystem path: stored
originals are named by item id.  Client names only become *metadata* (shown in
the UI and used as ZIP entry names), and are sanitised so that no entry can
climb out of its folder.
"""
from __future__ import annotations

import os
import posixpath
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import Callable, Iterable

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif"}
IGNORED_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
LOOSE_ROOT = "Photos"
EDITED_SUBFOLDER = "Edited - Airbnb"
EDITED_SUFFIX = " - Edited"
MAX_DEPTH = 16
MAX_NAME = 180

_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class UnsafePath(ValueError):
    pass


class ZipRejected(ValueError):
    """The archive as a whole cannot be accepted (message is shown to the user)."""


def clean_component(c: str) -> str:
    c = unicodedata.normalize("NFC", _CTRL.sub("", c)).strip()
    if len(c.encode("utf-8")) > MAX_NAME:
        stem, ext = os.path.splitext(c)
        while len((stem + ext).encode("utf-8")) > MAX_NAME and len(stem) > 1:
            stem = stem[:-1]
        c = stem + ext
    return c


def split_rel(raw: str) -> list[str]:
    """Split a client path into safe components.  Raises UnsafePath on traversal attempts."""
    raw = raw.replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise UnsafePath("absolute path")
    parts: list[str] = []
    for c in raw.split("/"):
        if c in ("", "."):
            continue
        if c == "..":
            raise UnsafePath("parent directory reference")
        c = clean_component(c)
        if not c or c in (".", ".."):
            raise UnsafePath("empty component")
        parts.append(c)
    if not parts:
        raise UnsafePath("empty path")
    if len(parts) > MAX_DEPTH:
        raise UnsafePath("too deep")
    return parts


def is_hidden_junk(parts: list[str]) -> bool:
    if parts[0].lower() == "__macosx":
        return True
    for c in parts:
        if c.startswith("."):
            return True
    return parts[-1].lower() in IGNORED_NAMES


def ext_of(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def kind_of(parts: list[str]) -> str:
    """'image' | 'zip' | 'junk' | 'unsupported'"""
    if is_hidden_junk(parts):
        return "junk"
    e = ext_of(parts[-1])
    if e in IMAGE_EXTS:
        return "image"
    if e == ".zip":
        return "zip"
    return "unsupported"


def with_root(parts: list[str]) -> list[str]:
    """Every photo lives under a root folder; loose files get a default one."""
    return parts if len(parts) > 1 else [LOOSE_ROOT, parts[0]]


def group_of(parts: list[str]) -> str:
    return "/".join(parts[:-1])


def out_ext_for(name: str) -> str | None:
    """Extension the edited file must have, or None to keep the original name exactly (e.g. 'IMG.JPG')."""
    return ".jpg" if ext_of(name) in (".heic", ".heif") else None


def out_rel_for(parts: list[str], ext: str | None = None) -> str:
    """Photos Al Khuzama/1/a.jpg -> 'Photos Al Khuzama - Edited/1/Edited - Airbnb/a.jpg'."""
    root, *mid, name = parts
    if ext is not None:
        name = os.path.splitext(name)[0] + ext
    return posixpath.join(root + EDITED_SUFFIX, *mid, EDITED_SUBFOLDER, name)


def dedupe(rel: str, taken: set[str]) -> str:
    """Case-insensitive de-duplication (macOS volumes are case-insensitive)."""
    key = unicodedata.normalize("NFC", rel).lower()
    if key not in taken:
        taken.add(key)
        return rel
    d, f = posixpath.split(rel)
    stem, ext = os.path.splitext(f)
    n = 2
    while True:
        cand = posixpath.join(d, f"{stem} ({n}){ext}")
        k = unicodedata.normalize("NFC", cand).lower()
        if k not in taken:
            taken.add(k)
            return cand
        n += 1


# --------------------------------------------------------------------------- ZIP
@dataclass
class ZipEntryResult:
    parts: list[str]
    tmp_path: str
    size: int


def _decode_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not (info.flag_bits & 0x800):
        try:  # Windows/old tools: cp437 bytes that are really UTF-8
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def extract_zip(
    zip_path: str,
    zip_stem: str,
    new_tmp: Callable[[], str],
    *,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> tuple[list[ZipEntryResult], dict[str, int]]:
    """Safely stream the photos out of an archive.

    Returns (entries, ignored_counts).  Entries are written to temp files chosen by the
    caller (`new_tmp`), never to a path derived from the archive.
    """
    ignored = {"unsupported": 0, "unsafe": 0, "encrypted": 0, "too_large": 0, "nested_zip": 0}
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ZipRejected("This is not a valid ZIP file")
    with zf:
        infos = zf.infolist()
        if len(infos) > 20000:
            raise ZipRejected("The ZIP contains too many entries")
        cands: list[tuple[zipfile.ZipInfo, list[str]]] = []
        declared_total = 0
        for info in infos:
            if info.is_dir():
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                ignored["unsafe"] += 1
                continue
            try:
                parts = split_rel(_decode_name(info))
            except UnsafePath:
                ignored["unsafe"] += 1
                continue
            k = kind_of(parts)
            if k == "junk":
                continue
            if k == "zip":
                ignored["nested_zip"] += 1
                continue
            if k != "image":
                ignored["unsupported"] += 1
                continue
            if info.flag_bits & 0x1:
                ignored["encrypted"] += 1
                continue
            if info.file_size > max_file_bytes:
                ignored["too_large"] += 1
                continue
            if info.compress_size and info.file_size / info.compress_size > 100:
                ignored["unsafe"] += 1          # decompression-bomb shaped
                continue
            declared_total += info.file_size
            cands.append((info, parts))
        if len(cands) > max_files:
            raise ZipRejected(f"The ZIP contains {len(cands)} photos; the limit per job is {max_files}")
        if declared_total > max_total_bytes:
            raise ZipRejected("The photos in this ZIP are larger than the per-job size limit")

        tops = {p[0] for _, p in cands if len(p) > 1}
        loose = any(len(p) == 1 for _, p in cands)
        prefix = [] if (len(tops) == 1 and not loose) else [zip_stem or LOOSE_ROOT]

        out: list[ZipEntryResult] = []
        written = 0
        for info, parts in cands:
            tmp = new_tmp()
            size = 0
            try:
                with zf.open(info) as src, open(tmp, "wb") as dst:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        size += len(chunk)
                        written += len(chunk)
                        if size > max_file_bytes or written > max_total_bytes:
                            raise ZipRejected("The ZIP expands to more data than allowed")
                        dst.write(chunk)
            except ZipRejected:
                _rm(tmp)
                for r in out:
                    _rm(r.tmp_path)
                raise
            except Exception:
                _rm(tmp)
                ignored["unsafe"] += 1
                continue
            out.append(ZipEntryResult(prefix + parts, tmp, size))
    return out, ignored


def _rm(p: str) -> None:
    try:
        os.remove(p)
    except OSError:
        pass
