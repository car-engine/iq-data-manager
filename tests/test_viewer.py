"""Tests for iqdm.viewer, the Viewer logic without Qt. Databases live in tmp_path."""

import sqlite3
from pathlib import Path

import pytest

from iqdm import viewer
from iqdm.db import repository as repo
from iqdm.db.connection import SchemaVersionError, write_transaction
from iqdm.db.version import SchemaStatus
from iqdm.models import (
    IN_PLACE_NOTE,
    ArchiveState,
    Channel,
    Endianness,
    IqLayout,
    Operation,
    Param,
    Recording,
    RecordingFilter,
    SampleType,
    TransferEntry,
    Verification,
)
from iqdm.scan.scanner import scan_recording
from iqdm.viewer import FilterInput, parse_filter

T0 = 1790733600.0  # 2026-09-30T02:00:00Z
DAY = 86400.0


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_empty_form_gives_an_empty_filter():
    assert parse_filter(FilterInput(), 8.0) == viewer.FilterResult(RecordingFilter())


def test_dates_are_read_at_the_display_offset():
    result = parse_filter(FilterInput(start_from="2026-09-30", start_to="2026-09-30"), 8.0)
    # 2026-09-30 00:00 at UTC+8 is 2026-09-29 16:00 UTC, which is T0 - 10 h.
    assert result.flt.start_from_unix == T0 - 10 * 3600
    assert result.flt.start_before_unix == T0 - 10 * 3600 + DAY  # "to" includes its day


def test_dates_at_utc():
    result = parse_filter(FilterInput(start_from="2026-09-30"), 0.0)
    assert result.flt.start_from_unix == T0 - 2 * 3600


@pytest.mark.parametrize(
    "text", ["30-09-2026", "2026-13-01", "2026-09-31", "yesterday", "2026/09/30"]
)
def test_a_wrong_date_is_an_error(text):
    result = parse_filter(FilterInput(start_from=text), 8.0)
    assert result.flt is None
    assert result.errors == ("Start date from: use the form YYYY-MM-DD, for example 2026-09-30.",)


def test_to_before_from_is_an_error():
    result = parse_filter(FilterInput(start_from="2026-09-30", start_to="2026-09-29"), 8.0)
    assert result.errors == ("Start date to is before Start date from.",)


def test_frequencies_are_mhz_and_exact():
    result = parse_filter(FilterInput(fc_min="145.8", fc_max="435"), 8.0)
    assert (result.flt.fc_min_hz, result.flt.fc_max_hz) == (145_800_000.0, 435_000_000.0)


@pytest.mark.parametrize("text", ["abc", "-5", "0", "1 MHz"])
def test_a_wrong_frequency_is_an_error(text):
    result = parse_filter(FilterInput(fc_max=text), 8.0)
    assert result.errors == (
        "Centre frequency max: enter a positive number in MHz, for example 145.8.",
    )


def test_max_below_min_is_an_error():
    result = parse_filter(FilterInput(fc_min="400", fc_max="300"), 8.0)
    assert result.errors == ("Centre frequency max is below min.",)


def test_errors_are_collected():
    result = parse_filter(FilterInput(start_to="x", fc_min="y"), 8.0)
    assert len(result.errors) == 2


def test_text_fields_are_stripped_and_blank_means_no_filter():
    form = FilterInput(
        band="  UHF ",
        rf_chain_text=" X310 ",
        remarks_text="   ",
        site_id=3,
        archive_state=ArchiveState.LOCAL,
    )
    flt = parse_filter(form, 8.0).flt
    assert (flt.band, flt.rf_chain_text, flt.remarks_text) == ("UHF", "X310", None)
    assert (flt.site_id, flt.archive_state) == (3, ArchiveState.LOCAL)


# ---------------------------------------------------------------------------
# Table text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0 s"),
        (12.9, "12 s"),
        (60, "1 m 00 s"),
        (2700, "45 m 00 s"),
        (3600, "1 h 00 m"),
        (7530, "2 h 05 m"),
        (90061, "25 h 01 m"),
    ],
)
def test_span_text(seconds, text):
    assert viewer.span_text(seconds) == text


@pytest.mark.parametrize(
    ("fc", "text"),
    [
        ((), ""),
        ((162e6,), "162"),
        ((433.92e6, 433.92e6), "433.92 \N{MULTIPLICATION SIGN} 2"),
        ((145.8e6, 435e6), "145.8 \N{MIDDLE DOT} 435"),
    ],
)
def test_fc_summary(fc, text):
    assert viewer.fc_summary(fc) == text


@pytest.mark.parametrize(
    ("coverage", "text"), [(1.0, "100.0%"), (0.9971, "99.7%"), (None, "unknown")]
)
def test_coverage_text(coverage, text):
    assert viewer.coverage_text(coverage) == text


@pytest.mark.parametrize(
    ("coverage", "threshold", "low"),
    [
        (0.961, 99.0, True),
        (0.99, 99.0, False),
        (0.98951, 99.0, False),  # shown as 99.0%, so not below 99
        (0.9894, 99.0, True),  # shown as 98.9%
        (1.0, 100.0, False),
        (None, 99.0, False),
    ],
)
def test_coverage_is_low_follows_the_shown_value(coverage, threshold, low):
    assert viewer.coverage_is_low(coverage, threshold) is low


def test_is_unverified_needs_archived_and_the_in_place_row():
    archived = Recording(
        logged_by="u",
        site_id=1,
        storage_root="r",
        rel_path="p",
        channels=[],
        archive_state=ArchiveState.ARCHIVED,
        archived_at="2026-09-18T05:00:00Z",
    )
    in_place = TransferEntry(
        recording_id=1,
        operation=Operation.CHECK,
        source="r",
        started_at="2026-09-18T05:00:00Z",
        performed_by="u",
        verification=Verification.SKIPPED,
        notes=IN_PLACE_NOTE,
    )
    assert viewer.is_unverified(archived, [in_place]) is True
    assert viewer.is_unverified(archived, []) is False
    other = TransferEntry(**{**in_place.__dict__, "notes": "other"})
    assert viewer.is_unverified(archived, [other]) is False
    local = Recording(**{**archived.__dict__, "archive_state": ArchiveState.LOCAL})
    assert viewer.is_unverified(local, [in_place]) is False


def test_size_and_state_text():
    assert viewer.size_text(None) == "unknown"
    assert viewer.size_text(57_600_000_000) == "57.6 GB"
    assert viewer.state_text(ArchiveState.LOCAL, False) == "local"
    assert viewer.state_text(ArchiveState.ARCHIVED, False) == "archived"
    assert viewer.state_text(ArchiveState.ARCHIVED, True) == "archived, not verified"
    assert viewer.state_text(ArchiveState.LOCAL, True) == "local"


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


def stored(**kw) -> Recording:
    base = {
        "logged_by": "userA",
        "site_id": 1,
        "storage_root": r"\\nas\recordings",
        "rel_path": r"2026\LocationA\rec128",
        "channels": [
            Channel(
                channel_index=0,
                sub_path="0",
                fc_hz=433.92e6,
                fs_hz=50e6,
                start_unix=T0,
                end_unix=T0 + 3600,
                n_files=3600,
            ),
            Channel(
                channel_index=1,
                sub_path="1",
                fc_hz=433.92e6,
                fs_hz=50e6,
                start_unix=T0,
                end_unix=T0 + 3600,
                n_files=3588,
            ),
        ],
        "params": [
            Param(param="SDR", value="USRP X310"),
            Param(param="LNA gain", value="10", unit="dB"),
            Param(param="Antenna", value="Monopole B", channel_index=1),
            Param(param="lna GAIN", value="20", unit="dB", channel_index=1),
            Param(param="SDR", value="USRP X310", channel_index=0),
        ],
    }
    base.update(kw)
    return Recording(**base)


def test_recording_rows_only_without_a_channel():
    rows = viewer.effective_params(stored(), None)
    assert [(r.scope, r.param, r.value) for r in rows] == [
        ("Recording", "SDR", "USRP X310"),
        ("Recording", "LNA gain", "10 dB"),
    ]


def test_a_channel_row_replaces_the_recording_row():
    rows = viewer.effective_params(stored(), 1)
    assert [(r.scope, r.param, r.value, r.note) for r in rows] == [
        ("Recording", "SDR", "USRP X310", ""),
        ("Ch 1", "Antenna", "Monopole B", ""),
        ("Ch 1", "lna GAIN", "20 dB", "replaces the Recording value 10 dB"),
    ]


def test_a_channel_row_that_repeats_the_recording_value_has_no_note():
    rows = viewer.effective_params(stored(), 0)
    assert [(r.scope, r.param, r.note) for r in rows] == [
        ("Recording", "LNA gain", ""),
        ("Ch 0", "SDR", ""),
    ]


def test_paths():
    rec = stored()
    assert viewer.recording_path(rec) == r"\\nas\recordings\2026\LocationA\rec128"
    assert viewer.channel_path(rec, rec.channels[1]) == r"\\nas\recordings\2026\LocationA\rec128\1"
    flat = Channel(channel_index=0, fc_hz=1.0, fs_hz=1.0, start_unix=T0, end_unix=T0 + 1)
    assert viewer.channel_path(rec, flat) == r"\\nas\recordings\2026\LocationA\rec128"


def test_format_text():
    assert viewer.format_text(stored()) == (
        "int16 \N{MIDDLE DOT} interleaved_iq \N{MIDDLE DOT} little-endian \N{MIDDLE DOT} "
        "no header \N{MIDDLE DOT} 1 s files"
    )
    other = stored(
        dtype=SampleType.FLOAT32,
        iq_layout=IqLayout.PLANAR_IQ,
        endianness=Endianness.BIG,
        header_bytes=1024,
        file_duration_s=0.5,
    )
    assert viewer.format_text(other) == (
        "float32 \N{MIDDLE DOT} planar_iq \N{MIDDLE DOT} big-endian \N{MIDDLE DOT} "
        "1,024-byte header \N{MIDDLE DOT} 0.5 s files"
    )


def transfer(**kw) -> TransferEntry:
    base = {
        "recording_id": 1,
        "operation": Operation.MOVE,
        "source": r"D:\captures\rec128",
        "destination": r"\\nas\recordings\rec128",
        "started_at": "2026-09-18T03:00:00Z",
        "finished_at": "2026-09-18T05:00:00Z",
        "performed_by": "userA",
        "n_files": 7188,
        "total_bytes": 1_440_000_000_000,
        "verification": Verification.PASS,
    }
    base.update(kw)
    return TransferEntry(**base)


def test_transfer_rows():
    rows = viewer.transfer_rows(
        [
            transfer(),
            transfer(
                operation=Operation.COPY,
                range_start_unix=T0,
                range_end_unix=T0 + 600,
                channels=(0, 2),
                n_files=None,
                total_bytes=None,
                finished_at=None,
            ),
            transfer(
                operation=Operation.CHECK, verification=Verification.SKIPPED, notes=IN_PLACE_NOTE
            ),
        ],
        8.0,
    )
    assert rows[0] == viewer.TransferRow(
        when="2026-09-18 11:00",
        operation="Move",
        scope="whole recording",
        result="7,188 files \N{MIDDLE DOT} 1.4 TB \N{MIDDLE DOT} verified",
        by="userA",
    )
    assert rows[1].scope == "2026-09-30 10:00:00 to 2026-09-30 10:10:00, channel 0, 2"
    assert rows[1].result == "not finished"
    assert rows[2].result.endswith("not verified")
    assert rows[2].notes == IN_PLACE_NOTE


# ---------------------------------------------------------------------------
# Gap scan
# ---------------------------------------------------------------------------


def test_gap_lines_and_timeline(make_recording):
    info = make_recording(n_channels=2, n_slots=20, channels={1: _gaps({3, 4, 10})})
    scan = scan_recording(Path(info.root), 1.0)
    assert viewer.gap_lines(scan, 0.0) == [
        "Ch 0: no gaps.",
        "Ch 1: 3 missing seconds in 2 gaps: 2026-09-30 02:00:03 (2 s), 2026-09-30 02:00:10 (1 s).",
    ]
    rows = viewer.timeline_rows(scan)
    assert [r.label for r in rows] == ["Ch 0", "Ch 1"]
    assert rows[1].gaps == ((T0 + 3, 2.0), (T0 + 10, 1.0))
    assert (rows[1].start_unix, rows[1].end_unix) == (T0, T0 + 20)


def _gaps(slots):
    from make_fixtures import ChannelSpec

    return ChannelSpec(gaps=frozenset(slots))


def test_gap_lines_list_ten_gaps_then_count(make_recording):
    info = make_recording(n_slots=40, gaps=frozenset(range(1, 30, 2)))  # 15 gaps
    lines = viewer.gap_lines(scan_recording(Path(info.root), 1.0), 0.0)
    assert lines[0].startswith("Ch 0: 15 missing seconds in 15 gaps: 2026-09-30 02:00:01 (1 s)")
    assert lines[0].endswith(", and 5 more.")
    assert lines[0].count("(1 s)") == 10


def test_gap_lines_for_a_channel_without_files(make_recording):
    info = make_recording(n_channels=2)
    (Path(info.root) / "2").mkdir()
    lines = viewer.gap_lines(scan_recording(Path(info.root), 1.0), 0.0)
    assert lines[-1] == "Ch 2: no data files."


def test_scan_differences(make_recording):
    info = make_recording(n_channels=2, n_slots=10, channels={1: _gaps({5})})
    scan = scan_recording(Path(info.root), 1.0)
    rec = stored(
        channels=[
            Channel(
                channel_index=0,
                fc_hz=1.0,
                fs_hz=1.0,
                start_unix=T0,
                end_unix=T0 + 10,
                n_files=10,
                total_bytes=40_000,
            ),
            Channel(
                channel_index=1, fc_hz=1.0, fs_hz=1.0, start_unix=T0, end_unix=T0 + 10, n_files=10
            ),
            Channel(channel_index=3, fc_hz=1.0, fs_hz=1.0, start_unix=T0, end_unix=T0 + 10),
        ]
    )
    assert viewer.scan_differences(rec, scan) == [
        "Channel 3 is in the database but not in the folder.",
        "Channel 1: the folder holds 9 files, the database lists 10.",
    ]


def test_scan_differences_names_sizes_and_new_channels(make_recording):
    info = make_recording(n_channels=2, n_slots=10)
    scan = scan_recording(Path(info.root), 1.0)
    rec = stored(
        channels=[
            Channel(
                channel_index=0,
                fc_hz=1.0,
                fs_hz=1.0,
                start_unix=T0,
                end_unix=T0 + 10,
                n_files=10,
                total_bytes=1,
            ),
        ]
    )
    assert viewer.scan_differences(rec, scan) == [
        "Channel 1 is in the folder but not in the database.",
        "Channel 0: the files hold 40.0 kB, the database lists 1 B.",
    ]


def test_scan_differences_is_empty_when_they_agree(make_recording):
    info = make_recording(n_channels=1, n_slots=10)
    scan = scan_recording(Path(info.root), 1.0)
    rec = stored(
        channels=[
            Channel(
                channel_index=0,
                fc_hz=1.0,
                fs_hz=1.0,
                start_unix=T0,
                end_unix=T0 + 10,
                n_files=10,
                total_bytes=40_000,
            ),
        ]
    )
    assert viewer.scan_differences(rec, scan) == []


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@pytest.fixture
def filled_db(db_path) -> tuple[Path, int]:
    def fill(conn):
        site = repo.add_site(conn, "LocationA").id
        repo.add_site(conn, "LocationB")
        rec = stored(
            site_id=site, archive_state=ArchiveState.ARCHIVED, archived_at="2026-09-18T05:00:00Z"
        )
        rec.channels[0].band = "UHF"
        rid = repo.insert_recording(conn, rec)
        repo.insert_transfer(conn, transfer(recording_id=rid))
        return rid

    return db_path, write_transaction(db_path, fill)


def set_user_version(path: Path, value: int) -> None:
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute(f"PRAGMA user_version = {value}")
    raw.close()


def test_load_list_and_choices(filled_db):
    db, rid = filled_db
    result = viewer.load_list(db, None)
    assert [s.id for s in result.summaries] == [rid]
    assert result.newer_database is False
    assert viewer.load_list(db, RecordingFilter(band="vhf")).summaries == []
    choices = viewer.load_choices(db)
    assert [s.name for s in choices.sites] == ["LocationA", "LocationB"]
    assert choices.bands == ["UHF"]


def test_load_details(filled_db):
    db, rid = filled_db
    details = viewer.load_details(db, rid)
    assert details.recording.id == rid
    assert details.site_name == "LocationA"
    assert [t.operation for t in details.transfers] == [Operation.MOVE]


def test_a_newer_database_is_read_with_a_flag(filled_db):
    db, rid = filled_db
    set_user_version(db, 99)
    result = viewer.load_list(db, None)
    assert result.newer_database is True
    assert [s.id for s in result.summaries] == [rid]


def test_a_database_without_a_version_is_refused(filled_db):
    db, _rid = filled_db
    set_user_version(db, 0)
    with pytest.raises(SchemaVersionError) as info:
        viewer.load_list(db, None)
    assert "not an IQ Data Manager database" in viewer.error_text(info.value)


def test_an_older_database_is_refused(filled_db, monkeypatch):
    db, _rid = filled_db
    monkeypatch.setattr("iqdm.db.version.LATEST_VERSION", 2)  # the file's version 1 is older
    with pytest.raises(SchemaVersionError) as info:
        viewer.load_list(db, None)
    assert "older version" in viewer.error_text(info.value)


def test_loading_never_changes_the_file(filled_db):
    db, rid = filled_db
    before = db.read_bytes()
    viewer.load_list(db, None)
    viewer.load_details(db, rid)
    viewer.load_choices(db)
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    ("exc", "start"),
    [
        (FileNotFoundError("x"), "Database file not found."),
        (
            SchemaVersionError(SchemaStatus.NEEDS_UPGRADE, "x"),
            "This database comes from an older version",
        ),
        (
            SchemaVersionError(SchemaStatus.NOT_IQDM, "x"),
            "This file is not an IQ Data Manager database.",
        ),
        (repo.NotFoundError("x"), "This recording is no longer in the database."),
        (OSError("x"), "Cannot read the database. Check the network connection"),
        (RuntimeError("x"), "Cannot read the database. Click Refresh"),
    ],
)
def test_error_text(exc, start):
    assert viewer.error_text(exc).startswith(start)
