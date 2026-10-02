"""Tests for iqdm.location (DECISIONS.md D14).

The paths are example strings. split_location() only parses them; no test opens a
network path or a drive other than the one that holds tmp_path.
"""

import sys
from pathlib import Path

import pytest

from iqdm.location import (
    Location,
    LocationError,
    join_location,
    mapped_drive_unc,
    split_location,
)
from iqdm.models import ArchiveState

NAS = r"\\nas\recordings"


def fake_resolver(mapping: dict[str, str]):
    calls: list[str] = []

    def resolve(drive: str) -> str | None:
        calls.append(drive)
        return mapping.get(drive)

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


def test_local_folder_splits_into_parent_and_name():
    loc = split_location(r"E:\captures\20260930_0200")
    assert loc == Location(
        storage_root=r"E:\captures",
        rel_path="20260930_0200",
        archive_state=ArchiveState.LOCAL,
    )
    assert loc.full_path == r"E:\captures\20260930_0200"


def test_folder_directly_on_a_drive_has_the_drive_root_as_storage_root():
    loc = split_location(r"E:\20260930_0200")
    assert (loc.storage_root, loc.rel_path) == ("E:\\", "20260930_0200")
    assert loc.full_path == r"E:\20260930_0200"


@pytest.mark.parametrize(
    "text",
    [
        r"E:\captures\20260930_0200\\",
        "E:/captures/20260930_0200",
        "E:/captures//20260930_0200/",
        r"E:\captures\x\..\20260930_0200",
        r"  E:\captures\20260930_0200  ",
    ],
)
def test_spellings_of_one_folder_give_one_location(text):
    loc = split_location(text)
    assert (loc.storage_root, loc.rel_path) == (r"E:\captures", "20260930_0200")


def test_folder_under_a_nas_root_is_archived_with_the_rest_as_rel_path():
    loc = split_location(NAS + r"\2026\20260930_0200", [NAS])
    assert loc == Location(
        storage_root=NAS,
        rel_path=r"2026\20260930_0200",
        archive_state=ArchiveState.ARCHIVED,
    )
    assert loc.full_path == NAS + r"\2026\20260930_0200"


def test_nas_match_ignores_case_and_keeps_the_configured_root():
    loc = split_location(r"\\NAS\Recordings\Site\Rec1", [NAS])
    assert loc.storage_root == NAS
    assert loc.rel_path == r"Site\Rec1"
    assert loc.archive_state is ArchiveState.ARCHIVED


def test_nas_root_matches_whole_components_only():
    loc = split_location(r"\\nas\recordings2\rec1", [NAS])
    assert loc.archive_state is ArchiveState.LOCAL
    assert loc.storage_root == r"\\nas\recordings2"
    assert loc.outside_nas_roots is True


def test_longest_nas_root_wins():
    inner = NAS + r"\iq"
    loc = split_location(NAS + r"\iq\rec1", [NAS, inner])
    assert (loc.storage_root, loc.rel_path) == (inner, "rec1")
    loc = split_location(NAS + r"\iq\rec1", [inner, NAS])
    assert (loc.storage_root, loc.rel_path) == (inner, "rec1")


def test_nas_root_given_with_forward_slashes_or_trailing_separator():
    loc = split_location(NAS + r"\rec1", ["//nas/recordings/"])
    assert (loc.storage_root, loc.rel_path) == (NAS, "rec1")


def test_mapped_drive_is_replaced_by_its_unc_path():
    resolve = fake_resolver({"Z:": NAS})
    loc = split_location(r"z:\2026\rec1", [NAS], resolve)
    assert (loc.storage_root, loc.rel_path) == (NAS, r"2026\rec1")
    assert loc.archive_state is ArchiveState.ARCHIVED
    assert resolve.calls == ["Z:"]


def test_drive_mapped_below_the_share_keeps_the_subfolder():
    resolve = fake_resolver({"Z:": NAS + r"\2026"})
    loc = split_location(r"Z:\rec1", [NAS], resolve)
    assert (loc.storage_root, loc.rel_path) == (NAS, r"2026\rec1")


def test_unmapped_drive_stays_local():
    resolve = fake_resolver({})
    loc = split_location(r"E:\captures\rec1", [NAS], resolve)
    assert (loc.storage_root, loc.rel_path) == (r"E:\captures", "rec1")
    assert loc.archive_state is ArchiveState.LOCAL
    assert loc.outside_nas_roots is False


def test_mapped_drive_outside_every_nas_root_is_local_and_flagged():
    resolve = fake_resolver({"Y:": r"\\otherserver\scratch"})
    loc = split_location(r"Y:\rec1", [NAS], resolve)
    assert loc == Location(
        storage_root=r"\\otherserver\scratch",
        rel_path="rec1",
        archive_state=ArchiveState.LOCAL,
        outside_nas_roots=True,
    )


def test_resolver_is_not_called_for_a_unc_path():
    resolve = fake_resolver({})
    split_location(NAS + r"\rec1", [NAS], resolve)
    assert resolve.calls == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "no folder"),
        ("captures\\rec1", "not an absolute path"),
        ("E:rec1", "not an absolute path"),
        ("E:\\", "drive or share root"),
        (r"\\nas\recordings", "drive or share root"),
        (r"\\?\E:\rec1", "device paths"),
    ],
)
def test_folders_that_cannot_be_logged(text, message):
    with pytest.raises(LocationError, match=message):
        split_location(text)


def test_nas_root_itself_cannot_be_logged():
    with pytest.raises(LocationError, match="NAS root"):
        split_location(NAS + r"\iq", [NAS + r"\iq"])


def test_mapped_drive_root_cannot_be_logged():
    with pytest.raises(LocationError, match="drive or share root"):
        split_location("Z:\\", [NAS], fake_resolver({"Z:": NAS}))


def test_join_location():
    assert join_location(NAS, r"2026\rec1") == NAS + r"\2026\rec1"
    assert join_location("E:\\", "rec1") == r"E:\rec1"


@pytest.mark.parametrize("drive", ["Z", "ZZ:", r"Z:\x", ""])
def test_mapped_drive_unc_rejects_malformed_drive(drive):
    with pytest.raises(ValueError, match="drive"):
        mapped_drive_unc(drive)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive mapping")
def test_mapped_drive_unc_is_none_for_the_local_drive_of_tmp_path(tmp_path):
    drive = Path(tmp_path).drive
    if not drive.endswith(":"):
        pytest.skip("tmp_path is not on a drive letter")
    assert mapped_drive_unc(drive) is None


@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows behaviour")
def test_mapped_drive_unc_is_none_off_windows():
    assert mapped_drive_unc("Z:") is None
