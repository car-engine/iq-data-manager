"""Tests for iqdm.transfer.pathcheck. Folders live under tmp_path.

UNC paths and drive roots appear only as strings. A destination that fails the
path-text checks is never opened, so those tests touch no drive or network.
"""

import dataclasses
from pathlib import Path, PureWindowsPath

import pytest

from conftest import recording_from
from iqdm.models import Operation
from iqdm.scan.scanner import scan_recording
from iqdm.transfer.pathcheck import (
    GB,
    MAX_FILE_PATH,
    DiskUsage,
    check_destination,
    windows_path,
)
from iqdm.transfer.selection import select_from_scan

PLENTY = DiskUsage(10**15, 0, 10**15)


def plenty(_path) -> DiskUsage:
    return PLENTY


@pytest.fixture
def selection(make_recording):
    info = make_recording(n_channels=2, n_slots=4)
    rec = recording_from(info)
    return select_from_scan(rec, scan_recording(Path(info.root), 1.0))


def check(selection, dest, operation=Operation.COPY, **kw):
    values = {
        "operation": operation,
        "margin_bytes": 0,
        "resolve_drive": None,
        "disk_usage": plenty,
        "long_paths": True,
    } | kw
    return check_destination(selection, dest, **values)


def copy_in(selection, dest: Path, rel_paths, size=None) -> None:
    """Copy some selected files into dest by hand, optionally with another size."""
    for rel in rel_paths:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (selection.source / rel).read_bytes()
        target.write_bytes(data if size is None else bytes(size))


# ---------------------------------------------------------------------------
# Path text
# ---------------------------------------------------------------------------


def test_a_new_folder_is_accepted(selection, tmp_path):
    result = check(selection, tmp_path / "out" / "rec")
    assert result.ok, result.errors
    assert result.notes == ()
    assert result.existing == frozenset()
    assert result.bytes_to_copy == selection.total_bytes


def test_an_empty_folder_is_accepted(selection, tmp_path):
    (tmp_path / "out").mkdir()
    assert check(selection, tmp_path / "out").ok


@pytest.mark.parametrize("dest", ["C:\\", "d:/", r"\\server\share", r"\\server\share\\"])
def test_a_drive_or_share_root_is_refused(selection, dest):
    result = check(selection, dest)
    assert result.errors == (
        f"The destination {dest} is a drive or a network share itself. Choose a folder in it.",
    )


@pytest.mark.parametrize("dest", ["out/rec", "D:", "D:rec"])
def test_a_relative_path_is_refused(selection, dest):
    result = check(selection, dest)
    assert result.errors == (f"The destination {dest} is not a full path.",)


def test_the_source_itself_is_refused(selection):
    dest = str(selection.source).upper() + "\\"
    assert check(selection, dest).errors == (
        "The destination is the source folder. Choose another folder.",
    )


def test_a_folder_inside_the_source_is_refused(selection):
    assert check(selection, selection.source / "0" / "copy").errors == (
        "The destination is inside the source folder. Choose a folder outside it.",
    )


def test_a_folder_that_holds_the_source_is_refused(selection):
    assert check(selection, selection.source.parent).errors == (
        "The source folder is inside the destination. Choose a new folder for the copy.",
    )


def test_a_mapped_drive_compares_as_its_unc_path(selection):
    nas_source = dataclasses.replace(selection, source=Path(r"\\nas\rec\rec1"))
    result = check(
        nas_source, r"z:\rec1\copy", resolve_drive=lambda d: r"\\nas\rec" if d == "Z:" else None
    )
    assert result.errors == (
        "The destination is inside the source folder. Choose a folder outside it.",
    )


def test_windows_path():
    assert windows_path(r"C:\a\..\b\\", None) == PureWindowsPath(r"C:\b")
    assert windows_path(r"Y:\x", lambda d: r"\\srv\s") == PureWindowsPath(r"\\srv\s\x")
    assert windows_path(r"Y:\x", lambda d: None) == PureWindowsPath(r"Y:\x")
    with pytest.raises(ValueError, match="not a full path"):
        windows_path("x\\y", None)


def test_only_a_copy_or_a_move_has_a_destination(selection, tmp_path):
    with pytest.raises(ValueError, match="copy or a move"):
        check(selection, tmp_path / "out", operation=Operation.CHECK)


# ---------------------------------------------------------------------------
# Destination content (D51)
# ---------------------------------------------------------------------------


def test_a_file_is_not_a_destination(selection, tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    assert check(selection, target).errors == (
        f"The destination {target} is a file. Choose a folder.",
    )


def test_a_copy_accepts_a_folder_with_other_files(selection, tmp_path):
    dest = tmp_path / "out"
    (dest / "0").mkdir(parents=True)
    (dest / "notes.txt").write_text("x", encoding="utf-8")
    (dest / "0" / "1790000000.dat").write_bytes(b"x")
    result = check(selection, dest)
    assert result.ok, result.errors
    assert result.notes == ("The destination already holds other files (2 files).",)


def test_a_copy_resumes_files_already_in_place(selection, tmp_path):
    dest = tmp_path / "out"
    done = [f.rel_path for f in selection.files[:3]]
    copy_in(selection, dest, done)
    (dest / (selection.files[3].rel_path + ".partial")).write_bytes(b"half")
    result = check(selection, dest)
    assert result.ok, result.errors
    assert result.existing == frozenset(done)
    assert result.bytes_to_copy == selection.total_bytes - 3 * 4000
    assert result.notes == (
        "Already in the destination with the right size: 3 files. They are not copied "
        "again and are checked with the rest.",
    )


def test_a_target_with_another_size_is_refused(selection, tmp_path):
    dest = tmp_path / "out"
    rel = selection.files[0].rel_path
    copy_in(selection, dest, [rel], size=10)
    (error,) = check(selection, dest).errors
    assert error == (
        "Files in the destination have the same name as a file to copy and another size "
        f"(1 file): {rel}. The copy never replaces a file. Choose another folder."
    )


def test_many_wrong_files_are_listed_ten_then_counted(make_recording, tmp_path):
    info = make_recording(n_slots=14)
    sel = select_from_scan(recording_from(info), scan_recording(Path(info.root), 1.0))
    dest = tmp_path / "out"
    copy_in(sel, dest, [f.rel_path for f in sel.files], size=1)
    (error,) = check(sel, dest).errors
    assert "another size (14 files)" in error
    assert ", and 4 more." in error


@pytest.fixture
def nas(tmp_path) -> Path:
    root = tmp_path / "nas"
    root.mkdir()
    return root


def move(selection, dest, nas_root, **kw):
    return check(selection, dest, Operation.MOVE, nas_roots=[str(nas_root)], **kw)


def test_a_move_goes_to_a_new_folder_under_a_nas_root(selection, nas):
    assert move(selection, nas / "2026" / "rec1", nas).ok


def test_a_move_outside_the_nas_roots_is_refused(selection, tmp_path, nas):
    dest = tmp_path / "local" / "rec1"
    assert move(selection, dest, nas).errors == (
        "An archive goes to a folder in one of the NAS locations in Settings. "
        f"{dest} is not in one.",
    )


def test_a_move_to_the_nas_root_itself_is_refused(selection, nas):
    (error,) = move(selection, nas, nas).errors
    assert error.startswith("The destination cannot hold a recording: a NAS root cannot")


def test_a_move_refuses_a_folder_with_other_files(selection, nas):
    dest = nas / "rec1"
    (dest / "extra").mkdir(parents=True)
    (dest / "readme.txt").write_text("x", encoding="utf-8")
    assert move(selection, dest, nas).errors == (
        "An archive needs a new or empty folder. The destination holds other files or "
        "folders: extra, readme.txt.",
    )


def test_a_move_resumes_its_own_files(selection, nas):
    dest = nas / "rec1"
    copy_in(selection, dest, [selection.files[0].rel_path])
    (dest / "1").mkdir()
    (dest / (selection.files[5].rel_path + ".partial")).write_bytes(b"half")
    result = move(selection, dest, nas)
    assert result.ok, result.errors
    assert result.existing == {selection.files[0].rel_path}


def test_links_in_the_destination_are_refused(selection, tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    try:
        (dest / "link").symlink_to(tmp_path)
    except OSError:
        pytest.skip("creating symbolic links needs a privilege this account lacks")
    assert check(selection, dest).errors == ("The destination holds links: link.",)


# ---------------------------------------------------------------------------
# Free space and path length
# ---------------------------------------------------------------------------


def test_free_space_must_cover_the_copy_and_the_margin(selection, tmp_path):
    need = selection.total_bytes + GB

    def usage(free):
        return lambda _path: DiskUsage(10**12, 0, free)

    assert check(selection, tmp_path / "out", margin_bytes=GB, disk_usage=usage(need)).ok
    (error,) = check(
        selection, tmp_path / "out", margin_bytes=GB, disk_usage=usage(need - 1)
    ).errors
    assert error.startswith("Not enough free space at the destination: the copy needs 32.0 kB")


def test_free_space_counts_only_files_still_to_copy(selection, tmp_path):
    dest = tmp_path / "out"
    copy_in(selection, dest, [f.rel_path for f in selection.files[:2]])
    free = selection.total_bytes - 2 * 4000
    result = check(selection, dest, disk_usage=lambda _p: DiskUsage(10**12, 0, free))
    assert result.ok, result.errors


def test_free_space_is_read_at_the_nearest_existing_folder(selection, tmp_path):
    seen = []

    def usage(path):
        seen.append(Path(path))
        return PLENTY

    check(selection, tmp_path / "a" / "b" / "c", disk_usage=usage)
    assert seen == [tmp_path]


def test_unreadable_free_space_is_an_error(selection, tmp_path):
    def usage(_path):
        raise OSError("device not ready")

    assert check(selection, tmp_path / "out", disk_usage=usage).errors == (
        "Cannot read the free space at the destination: device not ready",
    )


def test_long_paths_are_refused_unless_enabled(selection, tmp_path):
    dest = tmp_path / ("d" * (MAX_FILE_PATH - len(str(tmp_path))))
    errors = check(selection, dest, long_paths=False).errors
    assert len(errors) == 2
    assert errors[0].startswith("File paths in the destination would be")
    assert errors[1].startswith("Folder paths in the destination would be")
    assert check(selection, dest, long_paths=True).ok


def test_paths_within_the_limits_pass(selection, tmp_path):
    assert check(selection, tmp_path / "out", long_paths=False).ok
