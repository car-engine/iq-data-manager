"""Tests for iqdm.transfer.manifest. Manifests are written under tmp_path."""

import json
from pathlib import Path

import pytest

from iqdm.models import HashMode, Operation
from iqdm.transfer.manifest import (
    Manifest,
    ManifestError,
    ManifestFile,
    manifest_files,
    manifest_name,
    manifests_dir,
    parse_manifest,
    read_manifest,
    safe_rel_path,
    sha256_hex,
    to_bytes,
    write_manifest,
)

DIGEST = "0123456789abcdef" * 4


def manifest(**kw) -> Manifest:
    values = {
        "transfer_id": 7,
        "recording_id": 3,
        "operation": Operation.MOVE,
        "source": r"C:\captures\rec1",
        "destination": r"\\nas\recordings\2026\rec1",
        "range_start_unix": None,
        "range_end_unix": None,
        "channels": None,
        "hash_mode": HashMode.SAMPLE,
        "created_at": "2026-10-03T08:00:00Z",
        "files": (
            ManifestFile(path="0/1790733600.dat", size=4000, sha256=DIGEST),
            ManifestFile(path="0/1790733601.dat", size=4000),
            ManifestFile(path="1/1790733600.bin", size=3999),
        ),
    } | kw
    return Manifest(**values)


def test_write_and_read_round_trip(tmp_path):
    m = manifest(range_start_unix=1790733600.5, range_end_unix=1790733700.0, channels=(0, 1))
    path, digest = write_manifest(m, tmp_path / "manifests")
    assert path == tmp_path / "manifests" / "transfer-7-20261003T080000Z.json"
    assert digest == sha256_hex(path.read_bytes())
    assert read_manifest(path, digest) == m
    assert m.total_bytes == 11999


def test_the_file_is_readable_json(tmp_path):
    path, _ = write_manifest(manifest(), tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == "iqdm-manifest"
    assert data["files"][1] == {"path": "0/1790733601.dat", "size": 4000, "sha256": None}


def test_an_existing_manifest_is_never_replaced(tmp_path):
    path, _ = write_manifest(manifest(), tmp_path)
    before = path.read_bytes()
    with pytest.raises(ManifestError, match="already exists"):
        write_manifest(manifest(source=r"C:\other"), tmp_path)
    assert path.read_bytes() == before


def test_the_same_transfer_id_at_another_time_gets_its_own_file(tmp_path):
    first, _ = write_manifest(manifest(), tmp_path)
    second, _ = write_manifest(manifest(created_at="2026-11-01T00:00:00Z"), tmp_path)
    assert first != second
    assert len(list(tmp_path.iterdir())) == 2


def test_a_changed_manifest_is_refused(tmp_path):
    path, digest = write_manifest(manifest(), tmp_path)
    text = path.read_text(encoding="utf-8").replace('"size": 3999', '"size": 4000')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ManifestError, match="changed after it was written"):
        read_manifest(path, digest)


def test_a_missing_manifest_is_an_error(tmp_path):
    with pytest.raises(ManifestError, match="cannot read"):
        read_manifest(tmp_path / "transfer-1.json")


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/0/a.dat",
        "0//a.dat",
        "0/../a.dat",
        "../a.dat",
        "./a.dat",
        "0\\a.dat",
        "C:/a.dat",
        "a.dat:stream",
        "0/",
    ],
)
def test_unsafe_relative_paths_are_refused(path):
    with pytest.raises(ManifestError):
        safe_rel_path(path)


@pytest.mark.parametrize("path", ["a.dat", "0/1790733600.dat", "12/1790733600.5.BIN"])
def test_safe_relative_paths(path):
    assert safe_rel_path(path) == path


def test_writing_refuses_an_unsafe_path(tmp_path):
    bad = manifest(files=(ManifestFile(path="../x.dat", size=1),))
    with pytest.raises(ManifestError):
        write_manifest(bad, tmp_path)
    assert list(tmp_path.iterdir()) == []


def raw(**overrides) -> bytes:
    data = json.loads(to_bytes(manifest()))
    data.update(overrides)
    return json.dumps(data).encode("utf-8")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"format": "other"}, "not an IQ Data Manager manifest"),
        ({"version": 2}, "unknown manifest version"),
        ({"operation": "erase"}, "unknown value"),
        ({"hash_mode": "some"}, "unknown value"),
        ({"transfer_id": "7"}, "transfer_id"),
        ({"transfer_id": True}, "transfer_id"),
        ({"source": None}, "source"),
        ({"range_start_unix": "x"}, "range_start_unix"),
        ({"channels": [0, -1]}, "channels"),
        ({"files": {}}, "files"),
        ({"files": [{"path": "a.dat", "size": -1}]}, "valid size"),
        ({"files": [{"path": "a.dat", "size": 1, "sha256": "ABC"}]}, "SHA-256"),
        ({"files": [{"path": "a.dat", "size": 1}, {"path": "A.DAT", "size": 1}]}, "twice"),
        ({"files": [{"path": "../a.dat", "size": 1}]}, "relative path"),
    ],
)
def test_parse_refuses_wrong_content(overrides, message):
    with pytest.raises(ManifestError, match=message):
        parse_manifest(raw(**overrides))


def test_parse_refuses_text_that_is_not_json():
    with pytest.raises(ManifestError, match="not valid JSON"):
        parse_manifest(b"\xff{")


def test_names_and_folder():
    assert manifest_name(12, "2026-10-03T08:15:00Z") == "transfer-12-20261003T081500Z.json"
    assert manifests_dir(Path("C:/app/IQDataManager/config.toml")) == Path(
        "C:/app/IQDataManager/manifests"
    )


def test_manifest_files_keep_order_and_known_hashes():
    files = manifest_files([("b.dat", 2), ("a.dat", 1)], {"a.dat": DIGEST})
    assert files == (
        ManifestFile(path="b.dat", size=2),
        ManifestFile(path="a.dat", size=1, sha256=DIGEST),
    )
