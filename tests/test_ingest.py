import io, os, zipfile, stat
import pytest
from app import ingest


def test_split_rel_blocks_traversal_and_absolute():
    for bad in ["../x.jpg", "a/../../x.jpg", "/etc/passwd", "C:\\Windows\\x.jpg", "a/..", "..\\..\\x.jpg"]:
        with pytest.raises(ingest.UnsafePath):
            ingest.split_rel(bad)
    assert ingest.split_rel("A//b/./c.jpg") == ["A", "b", "c.jpg"]
    assert ingest.split_rel("A\\b\\c.jpg") == ["A", "b", "c.jpg"]
    assert ingest.split_rel("a/\x00b\x07/c.jpg") == ["a", "b", "c.jpg"]


def test_kinds():
    k = lambda p: ingest.kind_of(ingest.split_rel(p))
    assert k("a/b.JPG") == "image" and k("a/b.heic") == "image" and k("a/b.zip") == "zip"
    assert k("a/.DS_Store") == "junk" and k("a/._b.jpg") == "junk" and k("__MACOSX/a/b.jpg") == "junk" and k("a/Thumbs.db") == "junk"
    assert k("a/notes.txt") == "unsupported" and k("a/video.mov") == "unsupported"


def test_output_paths_mirror_the_upload_exactly():
    """Root folder and sub-folders keep their names; no 'Edited' / 'Airbnb' words are added anywhere."""
    f = lambda p: ingest.out_rel_for(ingest.with_root(ingest.split_rel(p)))
    assert f("Al Khuzama/1/img.jpg") == "Al Khuzama/1/img.jpg"
    assert f("Al Khuzama/02/b.jpg") == "Al Khuzama/02/b.jpg"
    assert f("Al Khuzama/a/b/img.jpg") == "Al Khuzama/a/b/img.jpg"
    assert f("Al Khuzama/img.jpg") == "Al Khuzama/img.jpg"
    assert f("loose.jpg") == "Photos/loose.jpg"
    assert ingest.out_rel_for(["R", "x.heic"], ".jpg") == "R/x.jpg"
    assert f("شقة الخزامة/غرفة ١/صورة.jpg") == "شقة الخزامة/غرفة ١/صورة.jpg"
    assert f("Trailing space /x.jpg") == "Trailing space /x.jpg"             # names are not trimmed
    assert ingest.out_ext_for("IMG_1.JPG") is None and ingest.out_ext_for("a.HEIC") == ".jpg"


def test_duplicate_filenames_are_kept_safely_and_case_insensitively():
    taken = set()
    got = [ingest.dedupe("R - Edited/Edited - Airbnb/IMG.jpg", taken) for _ in range(3)] + [ingest.dedupe("R - Edited/Edited - Airbnb/img.JPG", taken)]
    assert got == ["R - Edited/Edited - Airbnb/IMG.jpg", "R - Edited/Edited - Airbnb/IMG (2).jpg", "R - Edited/Edited - Airbnb/IMG (3).jpg", "R - Edited/Edited - Airbnb/img (4).JPG"]


def _zip(path, entries, symlink=None, flat_comp=False):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
        if symlink:
            zi = zipfile.ZipInfo(symlink[0]); zi.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(zi, symlink[1])


def _extract(tmp_path, zip_path, **kw):
    n = [0]
    def new_tmp():
        n[0] += 1; return str(tmp_path / f"t{n[0]}")
    args = dict(max_files=100, max_file_bytes=10_000_000, max_total_bytes=50_000_000)
    args.update(kw)
    return ingest.extract_zip(str(zip_path), "MyZip", new_tmp, **args)


def test_zip_slip_symlink_junk_and_unsupported_are_all_blocked(tmp_path):
    z = tmp_path / "evil.zip"
    _zip(z, [("Root/ok/a.jpg", b"A" * 100), ("../../evil.jpg", b"E"), ("/abs/evil.jpg", b"E"), ("C:\\x\\evil.jpg", b"E"),
             ("Root/__MACOSX/._a.jpg", b"x"), ("Root/.DS_Store", b"x"), ("Root/readme.txt", b"x"), ("Root/inner.zip", b"x")],
         symlink=("Root/link.jpg", "/etc/passwd"))
    ents, ign = _extract(tmp_path, z)
    assert [e.parts for e in ents] == [["Root", "ok", "a.jpg"]]
    assert ign["unsafe"] >= 4 and ign["unsupported"] == 1 and ign["nested_zip"] == 1
    assert not (tmp_path.parent / "evil.jpg").exists()                 # nothing escaped
    assert all(os.path.dirname(e.tmp_path) == str(tmp_path) for e in ents)


def test_zip_root_naming(tmp_path):
    one = tmp_path / "one.zip"; _zip(one, [("Photos Al Khuzama/1/a.jpg", b"1"), ("Photos Al Khuzama/2/b.jpg", b"2")])
    ents, _ = _extract(tmp_path, one); assert {e.parts[0] for e in ents} == {"Photos Al Khuzama"}
    many = tmp_path / "many.zip"; _zip(many, [("1/a.jpg", b"1"), ("2/b.jpg", b"2")])
    ents, _ = _extract(tmp_path, many); assert {e.parts[0] for e in ents} == {"MyZip"} and ents[0].parts[1] == "1"
    flat = tmp_path / "flat.zip"; _zip(flat, [("a.jpg", b"1"), ("b.jpg", b"2")])
    ents, _ = _extract(tmp_path, flat); assert [e.parts for e in ents] == [["MyZip", "a.jpg"], ["MyZip", "b.jpg"]]


def test_zip_limits_and_bombs(tmp_path):
    z = tmp_path / "big.zip"; _zip(z, [(f"R/{i}.jpg", b"x" * 10) for i in range(5)])
    with pytest.raises(ingest.ZipRejected):
        _extract(tmp_path, z, max_files=3)
    z2 = tmp_path / "bomb.zip"; _zip(z2, [("R/a.jpg", b"\0" * 5_000_000)])            # ~5000:1 ratio
    ents, ign = _extract(tmp_path, z2); assert ents == [] and ign["unsafe"] == 1
    z3 = tmp_path / "large.zip"; _zip(z3, [("R/a.jpg", os.urandom(50_000))])
    ents, ign = _extract(tmp_path, z3, max_file_bytes=10_000); assert ents == [] and ign["too_large"] == 1
    z4 = tmp_path / "total.zip"; _zip(z4, [("R/a.jpg", os.urandom(30_000)), ("R/b.jpg", os.urandom(30_000))])
    with pytest.raises(ingest.ZipRejected):
        _extract(tmp_path, z4, max_total_bytes=40_000)
    notzip = tmp_path / "n.zip"; notzip.write_bytes(b"hello")
    with pytest.raises(ingest.ZipRejected):
        _extract(tmp_path, notzip)


def test_legacy_encoded_arabic_names_are_repaired(tmp_path):
    """Old Windows/Mac tools write UTF-8 names without the UTF-8 flag; the archive reader then shows cp437 mojibake."""
    name = "شقة١/صورة.jpg"
    raw = name.encode("utf-8")
    placeholder = ("Q" * (len(raw) - 4)) + ".jpg"
    assert len(placeholder.encode()) == len(raw)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(placeholder, b"x" * 20)
    data = buf.getvalue().replace(placeholder.encode(), raw)            # local header + central directory, flag bit 11 stays 0
    z = tmp_path / "legacy.zip"; z.write_bytes(data)
    assert zipfile.ZipFile(z).infolist()[0].flag_bits & 0x800 == 0
    ents, _ = _extract(tmp_path, z)
    assert ents[0].parts == ["شقة١", "صورة.jpg"]        # single top-level folder is the root
