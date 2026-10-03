"""Tests for iqdm.movecopy: the Archive / copy tab's logic without Qt."""

import dataclasses
from pathlib import Path

import pytest

from conftest import recording_from
from iqdm import movecopy
from iqdm.config import Config
from iqdm.db import repository as repo
from iqdm.db.connection import write_transaction
from iqdm.entry import ItemState
from iqdm.models import ArchiveState, HashMode, Operation, TransferEntry, Verification
from iqdm.movecopy import (
    NOT_FINISHED,
    FormError,
    FormInput,
    LaptopStep,
    RateMeter,
    default_copy_destination,
    form_from_transfer,
    format_time_input,
    format_unix_input,
    laptop_copy,
    parse_time_input,
    parse_unix_input,
    preview_summary,
    request_from_form,
    unfinished_state,
)
from iqdm.transfer.copier import CopyItem, CopyProgress, copy_files, local_path
from iqdm.transfer.operations import TransferRequest, preview_transfer
from iqdm.transfer.pathcheck import DiskUsage
from iqdm.transfer.verify import VerifyProgress
from make_fixtures import ChannelSpec

T0 = 1790733600.0  # 2026-09-30T02:00:00Z

# ---------------------------------------------------------------------------
# Time input (D59)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("offset", "text"),
    [
        (8, "2026-09-30 10:00:00"),
        (0, "2026-09-30 02:00:00"),
        (5.5, "2026-09-30 07:30:00"),
        (-3.5, "2026-09-29 22:30:00"),
    ],
)
def test_time_input_reads_the_display_offset(offset, text):
    assert parse_time_input(text, offset) == T0
    assert format_time_input(T0, offset) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-09-30", T0 - 10 * 3600),  # midnight at UTC+8 is 16:00 UTC the day before
        ("2026-09-30 10:00", T0),
        ("2026-09-30T10:00:00", T0),
        ("  2026-09-30 10:00:00.5  ", T0 + 0.5),
    ],
)
def test_time_input_forms(text, expected):
    assert parse_time_input(text, 8) == expected


def test_time_input_with_a_fraction_of_a_second():
    assert parse_time_input("2026-09-30 10:00:00.5", 8) == T0 + 0.5
    assert format_time_input(T0 + 0.5, 8) == "2026-09-30 10:00:00.5"
    assert format_time_input(T0 + 0.25, 8) == "2026-09-30 10:00:00.25"
    assert format_time_input(T0 + 0.9999999, 8) == "2026-09-30 10:00:01"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("30/09/2026", "YYYY-MM-DD HH:MM:SS"),
        ("2026-09-30 10", "YYYY-MM-DD HH:MM:SS"),
        ("2026-02-30 10:00:00", "is not a valid date and time"),
        ("2026-09-30 25:00:00", "is not a valid date and time"),
        ("", "YYYY-MM-DD HH:MM:SS"),
    ],
)
def test_wrong_time_input_says_why(text, message):
    with pytest.raises(ValueError, match=message):
        parse_time_input(text, 8)


def test_unix_input():
    assert parse_unix_input(" 1790733600.5 ") == T0 + 0.5
    assert format_unix_input(T0) == "1790733600"
    assert format_unix_input(T0 + 0.5) == "1790733600.5"
    for bad in ("", "abc", "-1", "nan", "inf"):
        with pytest.raises(ValueError, match="number of seconds"):
            parse_unix_input(bad)


def test_time_label_names_the_zone():
    assert movecopy.time_label("From", 8) == "From (UTC+8)"
    assert movecopy.time_label("To", 0) == "To (UTC)"


# ---------------------------------------------------------------------------
# Form values and requests
# ---------------------------------------------------------------------------


@pytest.fixture
def rec(make_recording):
    return recording_from(make_recording(n_channels=2, n_slots=6), id=5, site_id=1)


def form(rec, **kw) -> FormInput:
    values = {
        "operation": Operation.COPY,
        "recording": rec,
        "whole": True,
        "channels": (0, 1),
        "destination": "D:\\work\\rec",
        "hash_mode": HashMode.SAMPLE,
    } | kw
    return FormInput(**values)


def test_a_whole_copy_with_every_channel(rec):
    assert request_from_form(form(rec)) == TransferRequest(
        recording_id=5,
        operation=Operation.COPY,
        destination="D:\\work\\rec",
        hash_mode=HashMode.SAMPLE,
    )


def test_a_copy_of_a_range_and_a_channel(rec):
    request = request_from_form(
        form(rec, whole=False, start_unix=T0 + 1, end_unix=T0 + 4, channels=(1,))
    )
    assert (request.start_unix, request.end_unix, request.channels) == (T0 + 1, T0 + 4, (1,))


def test_an_archive_always_takes_the_whole_recording(rec):
    request = request_from_form(
        form(
            rec,
            operation=Operation.ARCHIVE,
            whole=False,
            start_unix=T0 + 1,
            end_unix=T0 + 4,
            channels=(1,),
        )
    )
    assert (request.start_unix, request.end_unix, request.channels) == (None, None, None)


@pytest.mark.parametrize(
    ("change", "messages"),
    [
        ({"recording": None}, ("Choose a recording.",)),
        ({"destination": "  "}, ("Choose a destination folder.",)),
        ({"channels": ()}, ("Select at least one channel.",)),
        ({"whole": False}, ("Enter the start and the end of the range.",)),
        (
            {"whole": False, "start_unix": T0 + 4, "end_unix": T0 + 4},
            ("The end of the range must be after its start.",),
        ),
        (
            {"whole": False, "time_errors": ("Write the time as YYYY-MM-DD HH:MM:SS.",)},
            ("Write the time as YYYY-MM-DD HH:MM:SS.",),
        ),
    ],
)
def test_form_problems_are_listed(rec, change, messages):
    with pytest.raises(FormError) as refused:
        request_from_form(form(rec, **change))
    assert refused.value.messages == messages


def test_resume_fills_the_form_from_the_stored_transfer(rec):
    entry = TransferEntry(
        id=3,
        recording_id=5,
        operation=Operation.COPY,
        source="//nas/rec",
        destination="D:\\work\\part",
        range_start_unix=T0 + 1,
        range_end_unix=T0 + 4,
        channels=(1,),
        hash_mode=HashMode.ALL,
        started_at="2026-10-03T08:00:00Z",
        performed_by="userA",
    )
    values = form_from_transfer(entry, rec)
    assert values == FormInput(
        operation=Operation.COPY,
        recording=rec,
        whole=False,
        start_unix=T0 + 1,
        end_unix=T0 + 4,
        channels=(1,),
        destination="D:\\work\\part",
        hash_mode=HashMode.ALL,
    )
    request = request_from_form(values)
    assert (request.channels, request.start_unix, request.end_unix) == ((1,), T0 + 1, T0 + 4)
    whole = form_from_transfer(
        dataclasses.replace(entry, channels=None, range_start_unix=None, range_end_unix=None), rec
    )
    assert (whole.whole, whole.channels) == (True, (0, 1))


@pytest.mark.parametrize(
    ("root", "rel", "expected"),
    [
        (
            "D:\\work\\iq",
            "2026\\LocationA\\20260918_0300",
            "D:\\work\\iq\\2026\\LocationA\\20260918_0300",
        ),
        ("D:\\work\\iq\\", "rec1", "D:\\work\\iq\\rec1"),
        ("D:/work/iq", "rec1", "D:\\work\\iq\\rec1"),
        (None, "rec1", ""),
        ("  ", "rec1", ""),
    ],
)
def test_the_copy_destination_keeps_the_relative_path(root, rel, expected):
    """D60."""
    assert default_copy_destination(root, rel) == expected


# ---------------------------------------------------------------------------
# Preview lines
# ---------------------------------------------------------------------------


def plenty(_path) -> DiskUsage:
    return DiskUsage(10**15, 0, 10**15)


@pytest.fixture
def logged(db_path, make_recording):
    info = make_recording(n_channels=2, n_slots=6, channels={1: ChannelSpec(gaps=frozenset({3}))})

    def insert(conn):
        site = repo.add_site(conn, "SiteA").id
        return repo.insert_recording(conn, recording_from(info, site_id=site))

    return info, write_transaction(db_path, insert)


def preview_of(db_path, rid, dest, hash_mode=HashMode.SAMPLE, operation=Operation.COPY):
    request = TransferRequest(
        recording_id=rid, operation=operation, destination=str(dest), hash_mode=hash_mode
    )
    config = Config(hash_sample_fraction=0.25)
    return preview_transfer(
        db_path, request, config, resolve_drive=None, disk_usage=plenty, long_paths=True
    )


def texts(summary, state=None) -> list[str]:
    return [i.text for i in summary.lines if state is None or i.state is state]


def test_preview_summary_of_a_new_copy(db_path, logged, tmp_path):
    _, rid = logged
    summary = preview_summary(preview_of(db_path, rid, tmp_path / "pc" / "rec"), 110)
    assert summary.files == "11"
    assert summary.size == "44.0 kB"
    assert summary.missing == "Channel 1: 1 missing second"
    assert summary.time == "under a minute at 110 MB/s"
    assert texts(summary, ItemState.OK) == [
        "Destination checked: not a drive or share root, outside the source, no file would "
        "be replaced, enough free space."
    ]
    assert "The check after the copy compares every file's size and hashes 3 of 11 files." in texts(
        summary, ItemState.INFO
    )


@pytest.mark.parametrize(
    ("mode", "after"),
    [
        (HashMode.SAMPLE, "They are hashed with the rest after the copy."),
        (HashMode.NONE, "Their sizes are compared with the rest after the copy."),
    ],
)
def test_preview_describes_files_already_in_place(db_path, logged, tmp_path, mode, after):
    info, rid = logged
    dest = tmp_path / "pc" / "rec"
    first = preview_of(db_path, rid, dest, mode)
    items = [CopyItem(rel_path=f.rel_path, size=f.size) for f in first.selection.files[:4]]
    assert copy_files(Path(info.root), dest, items).ok
    summary = preview_summary(preview_of(db_path, rid, dest, mode), 110)
    assert (
        f"4 files already in the destination with the right size (16.0 kB). They are not "
        f"copied again. {after} 7 files to copy (28.0 kB)."
    ) in texts(summary, ItemState.INFO)


def test_preview_errors_come_first(db_path, logged, tmp_path):
    _, rid = logged
    dest = tmp_path / "pc" / "rec"
    first = preview_of(db_path, rid, dest).selection.files[0]
    target = local_path(dest, first.rel_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"other size")
    summary = preview_summary(preview_of(db_path, rid, dest), 110)
    assert summary.lines[0].state is ItemState.ERROR
    assert summary.lines[0].text.startswith("Files in the destination have the same name")
    assert texts(summary, ItemState.OK) == []


def test_file_list_counts_the_rest(db_path, logged, tmp_path):
    _, rid = logged
    preview = preview_of(db_path, rid, tmp_path / "pc" / "rec")
    names = movecopy.file_list(preview, limit=3)
    assert names[:3] == [f.rel_path for f in preview.selection.files[:3]]
    assert names[3] == "and 8 more"
    assert len(movecopy.file_list(preview)) == 11


# ---------------------------------------------------------------------------
# The laptop copy (D55)
# ---------------------------------------------------------------------------

NAS = "\\\\nas\\recordings"


@pytest.fixture
def archived_rec(make_recording):
    return recording_from(
        make_recording(n_slots=4),
        id=5,
        site_id=1,
        storage_root=NAS,
        rel_path="2026\\rec",
        archive_state=ArchiveState.ARCHIVED,
        archived_at="2026-10-03T08:00:00Z",
    )


def row(tid, operation, **kw) -> TransferEntry:
    values = {
        "id": tid,
        "recording_id": 5,
        "operation": operation,
        "source": "C:\\captures\\rec",
        "started_at": "2026-10-03T07:00:00Z",
        "finished_at": "2026-10-03T08:00:00Z",
        "performed_by": "userA",
        "verification": Verification.PASS,
    } | kw
    return TransferEntry(**values)


def archive(tid=1, **kw) -> TransferEntry:
    values = {"destination": NAS + "\\2026\\rec", "n_files": 10} | kw
    return row(tid, Operation.ARCHIVE, **values)


def check(tid=2, parent=1, **kw) -> TransferEntry:
    values = {"started_at": "2026-10-03T09:00:00Z", "finished_at": "2026-10-03T09:05:00Z"} | kw
    return row(tid, Operation.CHECK, parent_id=parent, destination=NAS + "\\2026\\rec", **values)


def delete(tid, n, parent=1) -> TransferEntry:
    return row(
        tid, Operation.DELETE, parent_id=parent, n_files=n, started_at="2026-10-03T10:00:00Z"
    )


def test_no_archive_means_nothing_to_delete(archived_rec):
    state = laptop_copy(archived_rec, [])
    assert state.step is LaptopStep.NONE
    assert not state.can_check and not state.can_delete
    elsewhere = archive(destination=NAS + "\\other")
    assert laptop_copy(archived_rec, [elsewhere]).step is LaptopStep.NONE
    failed = archive(verification=Verification.FAIL)
    assert laptop_copy(archived_rec, [failed]).step is LaptopStep.NONE


def test_after_an_archive_the_check_comes_first(archived_rec):
    state = laptop_copy(archived_rec, [archive()])
    assert state.step is LaptopStep.CHECK_NEEDED
    assert state.can_check and not state.can_delete
    assert state.text.startswith("The laptop copy in C:\\captures\\rec is still there.")


def test_a_passed_check_allows_the_delete(archived_rec):
    state = laptop_copy(archived_rec, [archive(), check()])
    assert state.step is LaptopStep.READY
    assert state.can_delete
    failed = laptop_copy(archived_rec, [archive(), check(verification=Verification.FAIL)])
    assert failed.step is LaptopStep.CHECK_NEEDED


def test_a_partly_deleted_copy_counts_what_remains(archived_rec):
    state = laptop_copy(archived_rec, [archive(), check(), delete(3, 4)])
    assert state.step is LaptopStep.PARTLY_DELETED
    assert state.files_left == 6
    assert state.can_delete
    assert state.text == "Partly deleted: 6 files remain in C:\\captures\\rec. Delete the rest."


def test_every_file_deleted(archived_rec):
    state = laptop_copy(archived_rec, [archive(), check(), delete(3, 4), delete(4, 6)])
    assert state.step is LaptopStep.DELETED
    assert not state.can_check and not state.can_delete


def test_the_latest_archive_at_the_location_counts(archived_rec):
    old = archive(1)
    new = archive(7, started_at="2026-10-04T07:00:00Z", finished_at="2026-10-04T08:00:00Z")
    state = laptop_copy(archived_rec, [old, check(2, parent=1), new])
    assert state.archive == new
    assert state.step is LaptopStep.CHECK_NEEDED


# ---------------------------------------------------------------------------
# Unfinished transfers, progress, speed
# ---------------------------------------------------------------------------


def test_unfinished_state():
    assert unfinished_state(archive(finished_at=None)) == NOT_FINISHED
    assert unfinished_state(archive(verification=Verification.SKIPPED)) == "Stopped"
    assert unfinished_state(archive(verification=Verification.FAIL)) == "Failed"


def test_progress_texts():
    p = CopyProgress(
        files_done=412, files_total=1194, bytes_done=98_200_000_000, bytes_total=238_800_000_000
    )
    assert movecopy.copy_progress_text(p) == "412 of 1,194 files, 98.2 GB of 238.8 GB"
    v = VerifyProgress(
        files_done=40, files_total=1194, bytes_done=1_200_000_000, bytes_total=12_000_000_000
    )
    assert movecopy.verify_progress_text(v) == (
        "Checked 40 of 1,194 files, hashed 1.2 GB of 12.0 GB"
    )
    assert movecopy.verify_progress_text(VerifyProgress(files_done=1, files_total=2)) == (
        "Checked 1 of 2 files"
    )
    assert (movecopy.percent(1, 3), movecopy.percent(5, 0), movecopy.percent(9, 4)) == (33, 0, 100)


def test_rate_meter_uses_the_last_ten_seconds():
    meter = RateMeter()
    assert meter.rate() is None
    meter.add(0.0, 0)
    assert meter.rate() is None
    for t in range(1, 31):
        rate = 10_000_000 if t <= 20 else 50_000_000  # 10 MB/s, then 50 MB/s
        meter.add(float(t), meter._samples[-1][1] + rate)
    assert meter.rate() == pytest.approx(50_000_000, rel=0.1)
    total = meter._samples[-1][1] + 500_000_000
    assert meter.seconds_left(total) == pytest.approx(10, rel=0.1)
    assert movecopy.speed_text(meter, total) == "50.0 MB/s, under a minute left"
