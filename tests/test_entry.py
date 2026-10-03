"""Tests for iqdm.entry: form input, checklist and saving. Data lives in tmp_path."""

import math
from dataclasses import replace
from pathlib import Path

import pytest

from iqdm import entry
from iqdm.db import repository as repo
from iqdm.db.connection import DatabaseBusyError, open_db
from iqdm.db.repository import ChannelRemovalError, DuplicateLocationError, DuplicateSiteError
from iqdm.entry import (
    TIMES,
    ChannelInput,
    EntryInput,
    ItemState,
    ParamInput,
    build_recording,
    can_save,
    channel_set_change,
    checklist,
    format_mhz,
    format_size,
    parse_mhz,
    save_edit,
    save_new,
    with_file_duration,
)
from iqdm.location import Location, split_location
from iqdm.models import (
    ArchiveState,
    Endianness,
    IqLayout,
    Operation,
    SameStart,
    SampleType,
    Verification,
)
from iqdm.scan.scanner import ChannelScan, DataFile, ScanResult, scan_recording
from make_fixtures import ChannelSpec

T0 = 1790733600  # 2026-09-30T02:00:00Z
FS_TEXT = "1k"  # make_fixtures default: 1 kS/s, int16, 4000 bytes per 1 s file
NAS = r"\\nas\recordings"
NOW = "2026-10-02T09:00:00Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def site_id(db_path) -> int:
    return entry.add_site(db_path, "SiteA").id


def scan_of(info):
    return scan_recording(Path(info.root), info.file_duration_s)


def form_for(scan, site_id: int | None, **kw) -> EntryInput:
    values = {
        "logged_by": "userA",
        "site_id": site_id,
        "channels": [
            ChannelInput(channel_index=c.channel_index, band="VHF", fc_mhz="145.8", fs_text=FS_TEXT)
            for c in scan.channels
        ],
    }
    values.update(kw)
    return EntryInput(**values)


def local_location(info) -> Location:
    return split_location(info.root)


def texts(items, state: ItemState | None = None) -> list[str]:
    return [i.text for i in items if state is None or i.state is state]


def ready_items(form, scan, location, **kw):
    """Checklist for a new entry after a scan and a duplicate check that found nothing."""
    return checklist(form, scan=scan, location=location, duplicate_checked=True, **kw)


def count(db_path, table: str) -> int:
    with open_db(db_path, readonly=True) as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


# ---------------------------------------------------------------------------
# Number and text formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "hz"),
    [
        ("145.8", 145_800_000.0),
        ("0.001", 1000.0),
        (" 10 ", 10_000_000.0),
        ("2400.000001", 2_400_000_001.0),
        ("1e3", 1_000_000_000.0),
    ],
)
def test_parse_mhz_is_exact(text, hz):
    assert parse_mhz(text) == hz


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "is empty"),
        ("  ", "is empty"),
        ("abc", "is not a number"),
        ("1,5", "is not a number"),
        ("nan", "is not a number"),
        ("inf", "is not a number"),
        ("0", "must be positive"),
        ("-3", "must be positive"),
    ],
)
def test_parse_mhz_rejects(text, reason):
    with pytest.raises(ValueError, match=reason):
        parse_mhz(text)


@pytest.mark.parametrize(
    ("hz", "text"),
    [(145_800_000.0, "145.8"), (100e6, "100"), (1000.0, "0.001"), (2_400_000_001.0, "2400.000001")],
)
def test_format_mhz(hz, text):
    assert format_mhz(hz) == text
    assert parse_mhz(text) == hz


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (0, "0 B"),
        (999, "999 B"),
        (4000, "4.0 kB"),
        (40_000_000, "40.0 MB"),
        (287_900_000_000, "287.9 GB"),
        (3 * 10**15, "3000.0 TB"),
    ],
)
def test_format_size(n, text):
    assert format_size(n) == text


def test_default_logged_by_uses_the_login_name(monkeypatch):
    monkeypatch.setattr("iqdm.entry.getpass.getuser", lambda: "userA")
    assert entry.default_logged_by() == "userA"


def test_default_logged_by_is_empty_when_the_name_is_unknown(monkeypatch):
    def fail() -> str:
        raise OSError("no user")

    monkeypatch.setattr("iqdm.entry.getpass.getuser", fail)
    assert entry.default_logged_by() == ""


# ---------------------------------------------------------------------------
# File duration
# ---------------------------------------------------------------------------


def test_with_file_duration_recomputes_gaps_and_end(make_recording):
    info = make_recording(n_slots=10, gaps=frozenset({4}))
    scan = scan_of(info)
    (gap,) = scan.channels[0].gaps
    assert gap.missing_seconds == 1.0

    halved = with_file_duration(scan, 0.5)
    ch = halved.channels[0]
    assert ch.file_duration_s == 0.5
    assert ch.end_unix == scan.channels[0].end_unix - 0.5
    # With 0.5 s files (D12), files 1 s apart leave 1 missing file (0.5 s) and the
    # 2 s step over slot 4 leaves 3 (1.5 s). Files: slots 0-3 and 5-9, so 8 steps.
    assert [g.missing_seconds for g in ch.gaps] == [0.5, 0.5, 0.5, 1.5, 0.5, 0.5, 0.5, 0.5]
    assert scan.channels[0].gaps == (gap,)  # the original is unchanged


def test_with_same_duration_returns_the_scan(make_recording):
    scan = scan_of(make_recording())
    assert with_file_duration(scan, 1.0) is scan


@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf])
def test_with_file_duration_rejects(make_recording, bad):
    scan = scan_of(make_recording())
    with pytest.raises(ValueError, match="positive"):
        with_file_duration(scan, bad)


# ---------------------------------------------------------------------------
# Checklist: new entry
# ---------------------------------------------------------------------------


def test_complete_entry_has_no_errors(make_recording):
    info = make_recording(n_channels=2, n_slots=10)
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    assert can_save(items)
    assert texts(items, ItemState.OK) == [
        "Folder scanned: 2 channels, 20 files",
        "Folder not already in the database",
        f"File sizes match fs {TIMES} 4 bytes: 4.0 kB per 1 s file",
        "Required fields filled",
    ]


def test_not_scanned_is_to_do():
    items = checklist(EntryInput(logged_by="u", site_id=1), scan=None)
    assert texts(items, ItemState.TODO) == ["Scan the folder"]
    assert texts(items, ItemState.ERROR) == []
    assert not can_save(items)


def test_folder_without_data_files_is_an_error(tmp_path):
    folder = tmp_path / "empty_rec"
    folder.mkdir()
    scan = scan_recording(folder, 1.0)
    items = ready_items(form_for(scan, 1), scan, split_location(str(folder)))
    assert "Folder scanned: no channel has data files" in texts(items, ItemState.ERROR)


def test_empty_channel_is_an_error(make_recording):
    info = make_recording(n_channels=2)
    Path(info.root, "2").mkdir()
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    assert any("channel 2 (folder 2) has no data files" in t for t in texts(items, ItemState.ERROR))
    assert not can_save(items)


def test_already_logged_is_an_error(make_recording):
    info = make_recording()
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info), logged_id=7)
    assert "Folder already logged as recording 7" in texts(items, ItemState.ERROR)


SAME_CAPTURE = (
    "Recording 9 has the same start, end and channels. It may be the same capture in "
    "another folder."
)


def twin(scan, rid=9, **kw) -> SameStart:
    """A logged recording with the times and channels of a scan of 1 s files."""
    values = {
        "recording_id": rid,
        "end_unix": max(c.files[-1].timestamp for c in scan.channels) + 1.0,
        "channel_indices": tuple(c.channel_index for c in scan.channels),
        "archive_state": ArchiveState.ARCHIVED,
    } | kw
    return SameStart(**values)


def test_the_same_capture_logged_elsewhere_is_information(make_recording):
    """D61: another recording with the same start, end and channels."""
    info = make_recording(n_channels=2, n_slots=5)
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info), same_start=[twin(scan)])
    assert SAME_CAPTURE in texts(items, ItemState.INFO)
    assert entry.can_save(items)


@pytest.mark.parametrize(
    "change",
    [{"end_unix": float(T0 + 6)}, {"channel_indices": (0,)}, {"recording_id": 7}],
)
def test_another_end_other_channels_or_the_same_folder_are_not_reported(make_recording, change):
    info = make_recording(n_channels=2, n_slots=5)
    scan = scan_of(info)
    items = ready_items(
        form_for(scan, 1),
        scan,
        local_location(info),
        logged_id=7,
        same_start=[twin(scan, **change)],
    )
    assert not any("same start, end and channels" in t for t in texts(items))


def test_the_end_follows_the_file_duration(make_recording):
    info = make_recording(n_slots=5)
    scan = scan_of(info)
    other = twin(scan, end_unix=float(T0 + 4 + 2))  # last file at T0 + 4, files of 2 s
    form = replace(form_for(scan, 1), file_duration_s=2.0)
    items = ready_items(
        form, with_file_duration(scan, 2.0), local_location(info), same_start=[other]
    )
    assert SAME_CAPTURE in texts(items, ItemState.INFO)
    at_one_second = ready_items(form_for(scan, 1), scan, local_location(info), same_start=[other])
    assert SAME_CAPTURE not in texts(at_one_second)


def test_find_same_start_reads_the_database(db_path, site_id, make_recording):
    info = make_recording(n_channels=2, n_slots=5)
    scan = scan_of(info)
    rec = build_recording(form_for(scan, site_id), scan=scan, location=local_location(info))
    rid = save_new(db_path, rec, now=NOW)
    (found,) = entry.find_same_start(db_path, scan)
    assert found == SameStart(
        recording_id=rid,
        end_unix=float(T0 + 5),
        channel_indices=(0, 1),
        archive_state=ArchiveState.LOCAL,
    )


def test_duplicate_check_must_run(make_recording):
    info = make_recording()
    scan = scan_of(info)
    items = checklist(form_for(scan, 1), scan=scan, location=local_location(info))
    assert "Not checked whether the folder is already logged" in texts(items, ItemState.ERROR)


def test_location_error_is_shown():
    items = checklist(EntryInput(), scan=None, location_error="a drive root cannot be logged")
    assert "Folder cannot be logged: a drive root cannot be logged" in texts(items, ItemState.ERROR)


def test_wrong_size_names_channel_and_sizes(make_recording):
    info = make_recording(wrong_size={3: 100})
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    (error,) = [t for t in texts(items, ItemState.ERROR)]
    assert "channel 0" in error
    assert "4000 bytes" in error
    assert "(100 bytes)" in error
    assert not any(t.startswith("File sizes match") for t in texts(items))


def test_wrong_fs_is_a_size_error(make_recording):
    info = make_recording()
    scan = scan_of(info)
    form = form_for(scan, 1)
    form.channels[0].fs_text = "2k"
    items = ready_items(form, scan, local_location(info))
    assert any(
        "differ from the expected size of 8000 bytes" in t for t in texts(items, ItemState.ERROR)
    )


def test_short_last_file_is_information(make_recording):
    info = make_recording(n_slots=5, wrong_size={4: None})
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    assert can_save(items)
    assert any("last file" in t and "shorter" in t for t in texts(items, ItemState.INFO))
    assert any(t.startswith("File sizes match") for t in texts(items, ItemState.OK))


def test_last_file_without_iq_data_is_an_error(make_recording):
    info = make_recording(n_slots=5, header_bytes=64, wrong_size={4: 64})
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1, header_bytes=64), scan, local_location(info))
    assert not can_save(items)


def test_fs_times_duration_not_whole_is_an_error(make_recording):
    info = make_recording()
    scan = scan_of(info)
    form = form_for(scan, 1)
    form.channels[0].fs_text = "1000.5"
    items = ready_items(form, scan, local_location(info))
    assert any("whole number of samples" in t for t in texts(items, ItemState.ERROR))


def test_different_fs_per_channel_gives_a_general_size_line(tmp_path):
    # make_fixtures uses one fs for every channel, so this scan is built by hand.
    def channel(index: int, size: int) -> ChannelScan:
        files = tuple(DataFile(name=f"{T0 + i}.dat", timestamp=T0 + i, size=size) for i in range(3))
        return ChannelScan(
            channel_index=index, sub_path=str(index), file_duration_s=1.0, files=files
        )

    scan = ScanResult(
        root=tmp_path,
        file_duration_s=1.0,
        channels=(channel(0, 4000), channel(1, 8000)),
        unrecognised=(),
    )
    form = form_for(scan, 1)
    form.channels[1].fs_text = "2k"
    items = ready_items(form, scan, split_location(str(tmp_path / "rec")))
    assert can_save(items)
    assert f"File sizes match fs {TIMES} 4 bytes in every channel" in texts(items, ItemState.OK)


def test_gaps_are_information(make_recording):
    info = make_recording(n_channels=2, channels={1: ChannelSpec(gaps=frozenset({3, 4, 5}))})
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    assert can_save(items)
    assert (
        "Channel 1 has 3 missing seconds in 1 gap. Ignore this if the gaps are expected."
        in texts(items, ItemState.INFO)
    )


def test_unrecognised_entries_are_information(make_recording):
    info = make_recording(junk=True)
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    assert can_save(items)
    (line,) = [t for t in texts(items, ItemState.INFO) if "not recognised" in t]
    assert line.startswith(f"{len(scan.unrecognised)} entries not recognised and ignored: ")


@pytest.mark.parametrize(
    ("change", "state", "message"),
    [
        ({"logged_by": "  "}, ItemState.TODO, "Enter the logged-by name"),
        ({"site_id": None}, ItemState.TODO, "Choose a site"),
        ({"file_duration_s": 0.0}, ItemState.ERROR, "File duration must be positive"),
        ({"header_bytes": -1}, ItemState.ERROR, "Header bytes must be 0 or more"),
    ],
)
def test_missing_required_field(make_recording, change, state, message):
    info = make_recording()
    scan = scan_of(info)
    form = form_for(scan, 1)
    for name, value in change.items():
        setattr(form, name, value)
    items = ready_items(form, scan, local_location(info))
    assert message in texts(items, state)
    assert "Required fields filled" not in texts(items)
    assert not can_save(items)


@pytest.mark.parametrize(
    ("field", "text", "state", "message"),
    [
        ("fc_mhz", "", ItemState.TODO, "Enter fc (MHz) for channel 0"),
        ("fs_text", " ", ItemState.TODO, "Enter fs for channel 0"),
        ("fc_mhz", "-1", ItemState.ERROR, "Channel 0: fc (MHz) must be positive: '-1'"),
        (
            "fs_text",
            "x",
            ItemState.ERROR,
            f"Channel 0: fs is not understood: 'x'. Enter {entry.FREQUENCY_HELP}",
        ),
        ("fs_text", "0", ItemState.ERROR, "Channel 0: fs must be positive: '0'"),
    ],
)
def test_channel_frequencies_are_required_and_positive(make_recording, field, text, state, message):
    info = make_recording()
    scan = scan_of(info)
    form = form_for(scan, 1)
    setattr(form.channels[0], field, text)
    items = ready_items(form, scan, local_location(info))
    assert message in texts(items, state)
    assert not can_save(items)


def test_empty_fields_are_grouped_into_one_to_do_line_each(make_recording):
    info = make_recording(n_channels=4)
    scan = scan_of(info)
    form = EntryInput(
        logged_by="u",
        channels=[ChannelInput(channel_index=c.channel_index) for c in scan.channels],
    )
    items = ready_items(form, scan, local_location(info))
    assert texts(items, ItemState.TODO) == [
        "Choose a site",
        "Enter fc (MHz) for channel 0, 1, 2, 3",
        "Enter fs for channel 0, 1, 2, 3",
    ]
    assert texts(items, ItemState.ERROR) == []


def test_channel_without_input_row_is_reported(make_recording):
    info = make_recording(n_channels=2)
    scan = scan_of(info)
    form = form_for(scan, 1)
    form.channels.pop()
    items = ready_items(form, scan, local_location(info))
    assert "Enter fc (MHz) for channel 1" in texts(items, ItemState.TODO)


def test_rf_chain_rows(make_recording):
    info = make_recording()
    scan = scan_of(info)
    form = form_for(
        scan,
        1,
        params=[
            ParamInput(param="SDR", value="USRP X310"),
            ParamInput(),  # blank rows are ignored
            ParamInput(param="", value="30", unit="dB", channel_index=0),
            ParamInput(param="Antenna", value=""),
            ParamInput(param="LNA gain", value="20", channel_index=3),
        ],
    )
    items = ready_items(form, scan, local_location(info))
    assert texts(items, ItemState.TODO) == [
        "RF chain row 3: enter the parameter name",
        "RF chain row 4 (Antenna): enter a value",
    ]
    assert texts(items, ItemState.ERROR) == [
        "RF chain row 5 (LNA gain): channel 3 is not in this recording",
    ]


def test_network_folder_outside_nas_roots_is_information(make_recording):
    info = make_recording()
    scan = scan_of(info)
    location = Location(
        storage_root=r"\\otherserver\scratch",
        rel_path="rec1",
        archive_state=ArchiveState.LOCAL,
        outside_nas_roots=True,
    )
    items = ready_items(form_for(scan, 1), scan, location)
    assert can_save(items)
    assert any("outside the configured NAS roots" in t for t in texts(items, ItemState.INFO))


def test_duration_change_without_rescan_changes_the_check(make_recording):
    info = make_recording(gaps=frozenset({4}))
    scan = with_file_duration(scan_of(info), 0.5)
    form = form_for(scan, 1, file_duration_s=0.5)
    items = ready_items(form, scan, local_location(info))
    # 1 kS/s for 0.5 s is 2000 bytes per file; the 4000-byte files are now wrong.
    assert any("expected size of 2000 bytes" in t for t in texts(items, ItemState.ERROR))


# ---------------------------------------------------------------------------
# build_recording and save_new
# ---------------------------------------------------------------------------


def test_build_recording_maps_scan_and_form(make_recording):
    info = make_recording(n_channels=2, n_slots=10, channels={1: ChannelSpec(first_slot=2)})
    scan = scan_of(info)
    form = form_for(
        scan,
        5,
        recording_plan_ref="  plan-7  ",
        remarks="",
        dtype=SampleType.INT16,
        iq_layout=IqLayout.INTERLEAVED_QI,
        endianness=Endianness.BIG,
        params=[ParamInput(param=" SDR ", value=" X310 ", unit=" "), ParamInput()],
    )
    form.channels[1].band = "  "
    loc = local_location(info)
    rec = build_recording(form, scan=scan, location=loc)
    assert (rec.storage_root, rec.rel_path) == (loc.storage_root, loc.rel_path)
    assert rec.archive_state is ArchiveState.LOCAL
    assert rec.archived_at is None
    assert rec.recording_plan_ref == "plan-7"
    assert rec.remarks is None
    assert rec.iq_layout is IqLayout.INTERLEAVED_QI
    assert rec.endianness is Endianness.BIG
    ch0, ch1 = rec.channels
    truth = info.channels
    assert (ch0.channel_index, ch0.sub_path, ch0.band) == (0, "0", "VHF")
    assert (ch0.fc_hz, ch0.fs_hz) == (145_800_000.0, 1000.0)
    assert (ch0.start_unix, ch0.end_unix) == (truth[0].start_unix, truth[0].end_unix)
    assert (ch0.n_files, ch0.total_bytes) == (truth[0].n_files, truth[0].total_bytes)
    assert ch1.band is None
    assert ch1.start_unix == truth[1].start_unix
    (param,) = rec.params
    assert (param.param, param.value, param.unit, param.channel_index) == (
        "SDR",
        "X310",
        None,
        None,
    )


def test_build_recording_needs_site_and_scan(make_recording):
    info = make_recording()
    scan = scan_of(info)
    with pytest.raises(ValueError, match="site"):
        build_recording(form_for(scan, None), scan=scan, location=local_location(info))
    with pytest.raises(ValueError, match="scan"):
        build_recording(form_for(scan, 1), scan=None, location=local_location(info))


def test_save_new_local_writes_no_transfer_row(db_path, site_id, make_recording):
    info = make_recording(n_channels=2)
    scan = scan_of(info)
    form = form_for(
        scan, site_id, params=[ParamInput(param="Gain", value="30", unit="dB", channel_index=1)]
    )
    rec = build_recording(form, scan=scan, location=local_location(info))
    rid = save_new(db_path, rec, now=NOW)
    with open_db(db_path, readonly=True) as c:
        stored = repo.get_recording(c, rid)
        assert repo.list_transfers(c, rid) == []
    assert stored.archive_state is ArchiveState.LOCAL
    assert stored.archived_at is None
    assert [ch.channel_index for ch in stored.channels] == [0, 1]
    assert [(p.param, p.channel_index) for p in stored.params] == [("Gain", 1)]
    assert stored.start_unix == info.channels[0].start_unix


def test_save_new_on_the_nas_writes_the_d2_row(db_path, site_id, make_recording):
    info = make_recording()
    scan = scan_of(info)
    location = Location(
        storage_root=NAS, rel_path=r"2026\rec1", archive_state=ArchiveState.ARCHIVED
    )
    rec = build_recording(form_for(scan, site_id), scan=scan, location=location)
    rid = save_new(db_path, rec, now=NOW)
    with open_db(db_path, readonly=True) as c:
        stored = repo.get_recording(c, rid)
        (row,) = repo.list_transfers(c, rid)
    assert stored.archive_state is ArchiveState.ARCHIVED
    assert stored.archived_at == NOW
    assert row.operation is Operation.CHECK
    assert row.verification is Verification.SKIPPED
    assert row.source == NAS + r"\2026\rec1"
    assert row.destination is None
    assert row.performed_by == "userA"
    assert row.notes == "logged in place, not verified against a source"
    assert (row.started_at, row.finished_at) == (NOW, NOW)
    assert row.hash_mode is None
    assert row.channels is None


def test_save_new_is_atomic(db_path, site_id, make_recording, monkeypatch):
    info = make_recording()
    scan = scan_of(info)
    location = Location(storage_root=NAS, rel_path="rec1", archive_state=ArchiveState.ARCHIVED)
    rec = build_recording(form_for(scan, site_id), scan=scan, location=location)

    def fail(conn, e):
        raise RuntimeError("crash before commit")

    monkeypatch.setattr("iqdm.entry.repository.insert_transfer", fail)
    with pytest.raises(RuntimeError):
        save_new(db_path, rec, now=NOW)
    assert count(db_path, "recordings") == 0
    assert count(db_path, "channels") == 0


def test_save_new_twice_is_a_duplicate(db_path, site_id, make_recording):
    info = make_recording()
    scan = scan_of(info)
    rec = build_recording(form_for(scan, site_id), scan=scan, location=local_location(info))
    rid = save_new(db_path, rec, now=NOW)
    assert entry.find_logged(db_path, local_location(info)) == rid
    with pytest.raises(DuplicateLocationError):
        save_new(db_path, rec, now=NOW)


def test_save_new_refuses_a_recording_with_an_id(db_path, site_id, make_recording):
    info = make_recording()
    scan = scan_of(info)
    rec = build_recording(form_for(scan, site_id), scan=scan, location=local_location(info))
    rec.id = 3
    with pytest.raises(ValueError, match="without an id"):
        save_new(db_path, rec)


def test_save_new_on_a_locked_database_is_busy(db_path, site_id, make_recording):
    info = make_recording()
    scan = scan_of(info)
    rec = build_recording(form_for(scan, site_id), scan=scan, location=local_location(info))
    with open_db(db_path) as holder:
        holder.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(DatabaseBusyError):
                save_new(db_path, rec, now=NOW, delays=())
        finally:
            holder.execute("ROLLBACK")
    assert count(db_path, "recordings") == 0


# ---------------------------------------------------------------------------
# Edit mode (DECISIONS.md D16)
# ---------------------------------------------------------------------------


def saved(db_path, site_id, info, **kw):
    """Save a recording of the fixture and return it as stored."""
    scan = scan_of(info)
    form = form_for(scan, site_id, **kw)
    rid = save_new(
        db_path, build_recording(form, scan=scan, location=local_location(info)), now=NOW
    )
    return entry.load_recording(db_path, rid)


def test_an_unchanged_form_changes_nothing(db_path, site_id, make_recording):
    info = make_recording(n_channels=2)
    params = [
        ParamInput(param="SDR", value="X310"),
        ParamInput(param="Gain", value="30", unit="dB", channel_index=1),
    ]
    original = saved(db_path, site_id, info, params=params, remarks="note")
    form = entry.input_from_recording(original)
    assert entry.edit_changes_nothing(original, build_recording(form, scan=None, original=original))
    reordered = replace(form, params=list(reversed(form.params)))  # params are a set (D7)
    assert entry.edit_changes_nothing(
        original, build_recording(reordered, scan=None, original=original)
    )
    rescanned = build_recording(form, scan=scan_of(info), original=original)
    assert entry.edit_changes_nothing(original, rescanned)  # the folder did not change


@pytest.mark.parametrize(
    "change",
    [
        {"remarks": "other"},
        {"logged_by": "someone"},
        {"recording_plan_ref": "plan"},
        {"iq_layout": IqLayout.PLANAR_IQ},
    ],
)
def test_a_changed_form_is_a_change(db_path, site_id, make_recording, change):
    info = make_recording()
    original = saved(db_path, site_id, info, remarks="note")
    form = entry.input_from_recording(original)
    edited = replace(form, **change)
    assert not entry.edit_changes_nothing(
        original, build_recording(edited, scan=None, original=original)
    )


def test_a_changed_channel_or_param_is_a_change(db_path, site_id, make_recording):
    info = make_recording(n_channels=2)
    original = saved(db_path, site_id, info, params=[ParamInput(param="SDR", value="X310")])
    form = entry.input_from_recording(original)
    fc = replace(form, channels=[replace(form.channels[0], fc_mhz="433.92"), form.channels[1]])
    unit = replace(form, params=[replace(form.params[0], unit="dB")])
    for edited in (fc, unit):
        assert not entry.edit_changes_nothing(
            original, build_recording(edited, scan=None, original=original)
        )


def test_input_from_recording_round_trip(db_path, site_id, make_recording):
    info = make_recording(n_channels=2)
    params = [
        ParamInput(param="SDR", value="X310"),
        ParamInput(param="Gain", value="30", unit="dB", channel_index=1),
    ]
    original = saved(
        db_path, site_id, info, params=params, remarks="note", recording_plan_ref="plan"
    )
    form = entry.input_from_recording(original)
    assert form.channels[0] == ChannelInput(
        channel_index=0, band="VHF", fc_mhz="145.8", fs_text="1 kHz"
    )
    assert form.params == [
        ParamInput(param="SDR", value="X310", unit="", channel_index=None),
        ParamInput(param="Gain", value="30", unit="dB", channel_index=1),
    ]
    items = checklist(form, scan=None, original=original)
    assert can_save(items)
    save_edit(db_path, build_recording(form, scan=None, original=original))
    again = entry.load_recording(db_path, original.id)
    for name in (
        "logged_by",
        "site_id",
        "storage_root",
        "rel_path",
        "channels",
        "file_duration_s",
        "dtype",
        "header_bytes",
        "archive_state",
        "archived_at",
        "recording_plan_ref",
        "remarks",
    ):
        assert getattr(again, name) == getattr(original, name), name
    assert [(p.param, p.value, p.unit, p.channel_index) for p in again.params] == [
        (p.param, p.value, p.unit, p.channel_index) for p in original.params
    ]


def test_edit_without_rescan_saves_metadata(db_path, site_id, make_recording):
    original = saved(db_path, site_id, make_recording())
    form = entry.input_from_recording(original)
    form.remarks = "checked"
    form.channels[0].fc_mhz = "433.92"
    form.channels[0].band = "UHF"
    form.iq_layout = IqLayout.PLANAR_IQ
    items = checklist(form, scan=None, original=original)
    assert "Not rescanned: the stored file counts and times are kept" in texts(
        items, ItemState.INFO
    )
    assert "File sizes not checked: the folder was not rescanned" in texts(items, ItemState.INFO)
    assert can_save(items)
    save_edit(db_path, build_recording(form, scan=None, original=original))
    again = entry.load_recording(db_path, original.id)
    assert again.remarks == "checked"
    assert again.iq_layout is IqLayout.PLANAR_IQ
    assert (again.channels[0].fc_hz, again.channels[0].band) == (433_920_000.0, "UHF")
    assert again.channels[0].n_files == original.channels[0].n_files
    assert count(db_path, "transfer_log") == 0


@pytest.mark.parametrize(
    "change",
    [
        lambda f: setattr(f.channels[0], "fs_text", "2k"),
        lambda f: setattr(f, "dtype", SampleType.INT8),
        lambda f: setattr(f, "header_bytes", 16),
        lambda f: setattr(f, "file_duration_s", 2.0),
    ],
)
def test_edit_of_size_fields_needs_a_rescan(db_path, site_id, make_recording, change):
    original = saved(db_path, site_id, make_recording())
    form = entry.input_from_recording(original)
    change(form)
    items = checklist(form, scan=None, original=original)
    assert not can_save(items)
    assert any("scan the folder again" in t for t in texts(items, ItemState.ERROR))


def test_edit_with_rescan_takes_counts_from_the_scan(db_path, site_id, make_recording):
    info = make_recording(n_slots=10)
    original = saved(db_path, site_id, info)
    Path(info.root, "0", "1790733610.dat").write_bytes(bytes(4000))
    scan = scan_of(info)
    form = entry.input_from_recording(original)
    items = checklist(form, scan=scan, original=original)
    assert can_save(items)
    assert "Folder not already in the database" not in texts(items)
    save_edit(db_path, build_recording(form, scan=scan, original=original))
    again = entry.load_recording(db_path, original.id)
    assert again.channels[0].n_files == 11
    assert again.end_unix == original.end_unix + 1


def test_edit_keeps_location_and_archive_state(db_path, site_id, make_recording):
    info = make_recording()
    scan = scan_of(info)
    location = Location(storage_root=NAS, rel_path="rec1", archive_state=ArchiveState.ARCHIVED)
    rid = save_new(
        db_path, build_recording(form_for(scan, site_id), scan=scan, location=location), now=NOW
    )
    original = entry.load_recording(db_path, rid)
    form = entry.input_from_recording(original)
    form.remarks = "edited"
    save_edit(db_path, build_recording(form, scan=scan, original=original))
    again = entry.load_recording(db_path, rid)
    assert (again.storage_root, again.rel_path) == (NAS, "rec1")
    assert (again.archive_state, again.archived_at) == (ArchiveState.ARCHIVED, NOW)
    assert count(db_path, "transfer_log") == 1


def test_channel_set_change(db_path, site_id, make_recording):
    info = make_recording(n_channels=2)
    original = saved(db_path, site_id, info)
    scan = scan_of(info)
    assert channel_set_change(original, scan) == entry.ChannelChange()

    other = scan_of(make_recording(n_channels=3, channels={0: ChannelSpec(first_slot=0)}))
    assert channel_set_change(original, other).added == (2,)

    single = scan_of(make_recording(n_channels=1))
    assert channel_set_change(original, single) == entry.ChannelChange(removed=(1,))


def test_rescan_that_removes_a_channel(db_path, site_id, make_recording):
    two = make_recording(n_channels=2)
    params = [
        ParamInput(param="SDR", value="X310"),
        ParamInput(param="Gain", value="30", channel_index=1),
        ParamInput(param="LNA", value="on", channel_index=1),
    ]
    original = saved(db_path, site_id, two, params=params)
    one = scan_of(make_recording(n_channels=1))
    form = entry.input_from_recording(original)
    form.params = [p for p in form.params if p.channel_index != 1]
    items = checklist(form, scan=one, original=original)
    assert "The rescan removes channel 1 and 2 parameters. Saving asks for confirmation." in texts(
        items, ItemState.INFO
    )
    assert can_save(items)
    assert entry.params_on_channels(original, [1]) == 2

    rec = build_recording(form, scan=one, original=original)
    with pytest.raises(ChannelRemovalError):
        save_edit(db_path, rec)
    assert len(entry.load_recording(db_path, original.id).channels) == 2

    save_edit(db_path, rec, allow_channel_removal=True)
    again = entry.load_recording(db_path, original.id)
    assert [c.channel_index for c in again.channels] == [0]
    assert [p.param for p in again.params] == ["SDR"]


def test_rescan_that_adds_a_channel_needs_its_frequencies(db_path, site_id, make_recording):
    original = saved(db_path, site_id, make_recording(n_channels=1))
    two = scan_of(make_recording(n_channels=2))
    form = entry.input_from_recording(original)
    items = checklist(form, scan=two, original=original)
    assert "The rescan adds channel 1." in texts(items, ItemState.INFO)
    assert "Enter fs for channel 1" in texts(items, ItemState.TODO)


def test_save_edit_needs_an_id(make_recording, db_path):
    info = make_recording()
    scan = scan_of(info)
    rec = build_recording(form_for(scan, 1), scan=scan, location=local_location(info))
    with pytest.raises(ValueError, match=r"rec\.id"):
        save_edit(db_path, rec)


def test_state_note():
    local = Location(storage_root="E:\\", rel_path="r", archive_state=ArchiveState.LOCAL)
    nas = Location(storage_root=NAS, rel_path="r", archive_state=ArchiveState.ARCHIVED)
    assert entry.state_note(local, None).startswith("Archive state on save: local.")
    assert entry.state_note(nas, None).startswith("Archive state on save: archived.")
    assert entry.state_note(None, None) == ""


# ---------------------------------------------------------------------------
# Database reads and sites
# ---------------------------------------------------------------------------


def test_load_choices(db_path, site_id, make_recording):
    entry.add_site(db_path, "alpha")
    saved(db_path, site_id, make_recording(), params=[ParamInput(param="SDR", value="X310")])
    choices = entry.load_choices(db_path)
    assert [s.name for s in choices.sites] == ["alpha", "SiteA"]
    assert choices.param_names == ["SDR"]
    assert choices.bands == ["VHF"]


def test_add_site_duplicate_ignoring_case(db_path, site_id):
    with pytest.raises(DuplicateSiteError):
        entry.add_site(db_path, "sitea")


def test_find_logged_is_none_for_a_new_folder(db_path, make_recording):
    assert entry.find_logged(db_path, local_location(make_recording())) is None


def test_add_site_strips_the_name(db_path):
    site = entry.add_site(db_path, "  New site ")
    assert site.name == "New site"
    with open_db(db_path, readonly=True) as c:
        assert repo.find_site(c, "new site").id == site.id


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(1.0, "1 missing second"), (3.0, "3 missing seconds"), (0.5, "0.5 missing seconds")],
)
def test_missing_text(seconds, text):
    assert entry.missing_text(seconds) == text


def test_params_without_channels_keeps_recording_rows_and_other_channels():
    rows = [
        ParamInput(param="SDR", value="X310"),
        ParamInput(param="Gain", value="30", channel_index=1),
        ParamInput(param="LNA", value="on", channel_index=0),
        ParamInput(param="Gain", value="20", channel_index=2),
    ]
    kept = entry.params_without_channels(rows, [1, 2])
    assert [(p.param, p.channel_index) for p in kept] == [("SDR", None), ("LNA", 0)]
    assert entry.params_without_channels(rows, []) == rows


# ---------------------------------------------------------------------------
# fs from the file size (D21), duration from the file names and coverage (D22)
# ---------------------------------------------------------------------------


def hand_channel(sizes, *, index=0, step=1.0, duration=1.0) -> ChannelScan:
    files = tuple(
        DataFile(name=f"{T0 + i * step}.dat", timestamp=T0 + i * step, size=s)
        for i, s in enumerate(sizes)
    )
    return ChannelScan(
        channel_index=index, sub_path=str(index), file_duration_s=duration, files=files
    )


@pytest.mark.parametrize(
    ("spec", "dtype", "header", "duration", "fs_hz"),
    [
        ({}, SampleType.INT16, 0, 1.0, 1000.0),
        ({"dtype": "int8", "header_bytes": 64}, SampleType.INT8, 64, 1.0, 1000.0),
        ({"dtype": "float32"}, SampleType.FLOAT32, 0, 1.0, 1000.0),
        ({"file_duration_s": 0.5}, SampleType.INT16, 0, 0.5, 1000.0),
        ({"fs_hz": 2500.0}, SampleType.INT16, 0, 1.0, 2500.0),
    ],
)
def test_infer_fs_from_fixture(make_recording, spec, dtype, header, duration, fs_hz):
    info = make_recording(**spec)
    channel = scan_recording(Path(info.root), duration).channels[0]
    result = entry.infer_fs(channel, dtype=dtype, header_bytes=header, file_duration_s=duration)
    assert result.fs_hz == fs_hz
    assert result.file_bytes == info.channels[0].expected_file_bytes


def test_infer_fs_follows_the_sample_type():
    channel = hand_channel([200_000_000] * 3)
    fs = {
        t: entry.infer_fs(channel, dtype=t, header_bytes=0, file_duration_s=1.0).fs_hz
        for t in SampleType
    }
    assert fs == {SampleType.INT8: 100e6, SampleType.INT16: 50e6, SampleType.FLOAT32: 25e6}


def test_infer_fs_ignores_a_short_last_file_and_odd_files():
    channel = hand_channel([4000, 4000, 4000, 100, 4000, 1234])
    assert entry.typical_file_bytes(channel) == 4000
    result = entry.infer_fs(channel, dtype="int16", header_bytes=0, file_duration_s=1.0)
    assert result.fs_hz == 1000.0


def test_typical_file_bytes_single_file_and_ties():
    assert entry.typical_file_bytes(hand_channel([4000])) == 4000
    assert entry.typical_file_bytes(hand_channel([4000, 8000, 1])) == 8000
    assert entry.typical_file_bytes(hand_channel([])) is None


@pytest.mark.parametrize(
    ("sizes", "header", "reason"),
    [
        ([4001, 4001], 0, "is not a whole number of int16 samples (4 bytes each)"),
        ([64, 64], 64, "holds no samples after a 64-byte header"),
        ([], 0, "the channel has no data files"),
    ],
)
def test_infer_fs_gives_a_reason_when_it_cannot(sizes, header, reason):
    result = entry.infer_fs(
        hand_channel(sizes), dtype="int16", header_bytes=header, file_duration_s=1.0
    )
    assert result.fs_hz is None
    assert reason in result.reason


def test_infer_fs_with_a_header_never_guesses_it():
    channel = hand_channel([4064] * 3)
    no_header = entry.infer_fs(channel, dtype="int16", header_bytes=0, file_duration_s=1.0)
    assert no_header.fs_hz == 1016.0
    with_header = entry.infer_fs(channel, dtype="int16", header_bytes=64, file_duration_s=1.0)
    assert with_header.fs_hz == 1000.0


def test_typical_spacing(make_recording):
    assert entry.typical_spacing(scan_of(make_recording())) == 1.0
    half = make_recording(file_duration_s=0.5)
    assert entry.typical_spacing(scan_recording(Path(half.root), 0.5)) == 0.5
    gappy = make_recording(n_slots=20, gaps=frozenset({3, 4, 5, 9, 10}))
    assert entry.typical_spacing(scan_of(gappy)) == 1.0
    assert entry.typical_spacing(scan_of(make_recording(n_slots=1))) is None


def test_duration_that_disagrees_with_the_file_names_is_an_error(make_recording):
    info = make_recording(file_duration_s=0.5, n_slots=40)
    scan = scan_of(info)  # the form keeps the default file duration of 1.0 s
    form = form_for(scan, 1)
    form.channels[0].fs_text = "500"  # 2000-byte files at 1.0 s and int16
    items = ready_items(form, scan, local_location(info))
    errors = texts(items, ItemState.ERROR)
    assert (
        "The file names are 0.5 s apart, but the file duration is 1 s. Set the file "
        "duration to match the files." in errors
    )
    assert (
        "Channel 0: coverage is 195.1%, so the files overlap in time. Check the file duration."
        in errors
    )
    assert not can_save(items)


def test_folder_07_case_is_caught_without_inference(make_recording):
    """Duration left at 1.0 s with fs typed to match the size: still an error (D22)."""
    info = make_recording(file_duration_s=0.5, n_slots=40)
    scan = scan_of(info)
    form = form_for(scan, 1)
    form.channels[0].fs_text = "500"
    assert not can_save(ready_items(form, scan, local_location(info)))
    fixed = with_file_duration(scan, 0.5)
    form = form_for(fixed, 1, file_duration_s=0.5, file_duration_inferred=True)
    items = ready_items(form, fixed, local_location(info))
    assert can_save(items), texts(items)
    assert "File duration set to 0.5 s from the spacing of the file names." in texts(
        items, ItemState.INFO
    )


def test_coverage_at_exactly_100_percent_is_fine(make_recording):
    info = make_recording(n_slots=10)
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    assert not any("coverage is" in t for t in texts(items))


def test_coverage_above_100_percent_in_edit_mode_without_rescan(db_path, site_id, make_recording):
    original = saved(db_path, site_id, make_recording())
    original.channels[0].n_files = 20  # as if a stored count were wrong
    form = entry.input_from_recording(original)
    items = checklist(form, scan=None, original=original)
    assert (
        "Channel 0: coverage is 200.0%, so the files overlap in time. Check the file duration."
        in texts(items, ItemState.ERROR)
    )


def test_inferred_fs_is_reported_with_its_basis(make_recording):
    info = make_recording(n_channels=2)
    scan = scan_of(info)
    form = form_for(scan, 1)
    for c in form.channels:
        c.fs_inferred = True
    items = ready_items(form, scan, local_location(info))
    assert (
        "fs filled in from the file size for channel 0, 1: 1 kHz (4.0 kB per 1 s file, "
        "int16, no header). Check it against the recording plan." in texts(items, ItemState.INFO)
    )
    assert can_save(items)


def test_fs_that_cannot_be_filled_in_says_why(make_recording):
    info = make_recording(header_bytes=2)  # 4002-byte files: not whole int16 samples
    scan = scan_of(info)
    form = form_for(scan, 1)
    form.channels[0].fs_text = ""
    items = ready_items(form, scan, local_location(info))
    assert any(
        t.startswith(
            "Channel 0: fs could not be filled in from the file size, because a "
            "4002-byte file with no header is not a whole number of int16 samples"
        )
        for t in texts(items, ItemState.INFO)
    )
    assert "Enter fs for channel 0" in texts(items, ItemState.TODO)


def test_scan_problems_are_an_error():
    items = checklist(EntryInput(), scan=None, scan_problems=("a", "b"))
    assert texts(items, ItemState.ERROR) == [
        "The scan stopped with 2 problems. Fix the folder and scan again: a; b"
    ]
    assert "Scan the folder" not in texts(items)


def test_empty_channel_is_an_error_before_fs_is_entered(make_recording):
    info = make_recording(n_channels=2)
    Path(info.root, "2").mkdir()
    scan = scan_of(info)
    form = form_for(scan, 1)
    form.channels.pop()  # no input row for channel 2, so no fs either
    items = ready_items(form, scan, local_location(info))
    assert "channel 2 (folder 2) has no data files" in texts(items, ItemState.ERROR)


# ---------------------------------------------------------------------------
# fs with units (DECISIONS.md D25)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "hz"),
    [
        ("1000", 1000.0),
        ("1000 Hz", 1000.0),
        ("100k", 100_000.0),
        ("100 k", 100_000.0),
        ("12.5kHz", 12_500.0),
        ("12.5 kHz", 12_500.0),
        ("1.5M", 1_500_000.0),
        ("10 MHz", 10_000_000.0),
        ("2G", 2e9),
        ("2.4 GHz", 2.4e9),
        ("0.5", 0.5),
        ("1.", 1.0),
        (".5k", 500.0),
        ("1e3k", 1e6),
        ("  30.72M  ", 30_720_000.0),
    ],
)
def test_parse_frequency(text, hz):
    assert entry.parse_frequency(text) == hz


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "is empty"),
        ("10m", "is not understood"),
        ("10 mhz", "is not understood"),
        ("10 K", "is not understood"),
        ("10 kHz2", "is not understood"),
        ("10 Hz Hz", "is not understood"),
        ("1,5M", "is not understood"),
        ("-1k", "is not understood"),
        ("abc", "is not understood"),
        ("M", "is not understood"),
        ("0", "must be positive"),
        ("0 k", "must be positive"),
    ],
)
def test_parse_frequency_rejects(text, reason):
    with pytest.raises(ValueError, match=reason):
        entry.parse_frequency(text)


@pytest.mark.parametrize(
    ("hz", "text"),
    [
        (500.0, "500 Hz"),
        (0.5, "0.5 Hz"),
        (1000.0, "1 kHz"),
        (12_500.0, "12.5 kHz"),
        (1_920_000.0, "1.92 MHz"),
        (50e6, "50 MHz"),
        (2.4e9, "2.4 GHz"),
        (2_457_600.0, "2.4576 MHz"),
    ],
)
def test_format_frequency_reads_back(hz, text):
    assert entry.format_frequency(hz) == text
    assert entry.parse_frequency(text) == hz


def test_stored_fs_appears_with_a_unit_in_edit_mode(db_path, site_id, make_recording):
    original = saved(db_path, site_id, make_recording())
    assert entry.input_from_recording(original).channels[0].fs_text == "1 kHz"


# ---------------------------------------------------------------------------
# Folder named like a channel folder (DECISIONS.md D27)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("folder", "parent"),
    [
        (r"E:\captures\rec1\0", r"E:\captures\rec1"),
        (r"E:\captures\rec1\12", r"E:\captures\rec1"),
        (r"E:\captures\rec1\999", r"E:\captures\rec1"),
        (r"E:\captures\rec1\1000", None),
        (r"E:\captures\1790733600", None),
        (r"E:\captures\01", None),
        (r"E:\captures\20260930_0200", None),
    ],
)
def test_channel_like_parent(folder, parent):
    assert entry.channel_like_parent(split_location(folder)) == parent


def test_channel_like_folder_is_a_warning(make_recording):
    info = make_recording(n_channels=2)
    folder = Path(info.root, "0")
    scan = scan_recording(folder, 1.0)
    location = split_location(str(folder))
    items = ready_items(form_for(scan, 1), scan, location)
    assert texts(items)[0] == (
        "This folder is named like a channel folder. If it belongs to a recording, "
        f"choose the parent folder: {location.storage_root}"
    )
    assert items[0].state is ItemState.INFO
    assert can_save(items)


def test_channel_like_folder_is_not_reported_in_edit_mode(db_path, site_id, make_recording):
    original = saved(db_path, site_id, make_recording())
    original.rel_path = "0"
    form = entry.input_from_recording(original)
    location = Location(
        storage_root=original.storage_root, rel_path="0", archive_state=ArchiveState.LOCAL
    )
    items = checklist(form, scan=None, location=location, original=original)
    assert not any("named like a channel folder" in t for t in texts(items))


# ---------------------------------------------------------------------------
# RF chain repeats, overrides and conflicts (DECISIONS.md D28)
# ---------------------------------------------------------------------------


def rf_items(make_recording, params, known=(), n_channels=3):
    info = make_recording(n_channels=n_channels)
    scan = scan_of(info)
    form = form_for(scan, 1, params=params)
    items = ready_items(form, scan, local_location(info), known_param_names=known)
    return form, scan, info, items


def test_users_example_gives_information_only(make_recording):
    params = [
        ParamInput(param="Antenna", value="Omni"),
        ParamInput(param="Antenna", value="Omni", channel_index=0),
        ParamInput(param="Antenna", value="LogP", channel_index=1),
        ParamInput(param="antenna", value="Omni", channel_index=2),
    ]
    form, scan, info, items = rf_items(make_recording, params)
    assert can_save(items)
    infos = texts(items, ItemState.INFO)
    assert "Ch 0: Antenna repeats the Recording value." in infos
    assert "Ch 1: Antenna is LogP; the Recording value Omni applies to the other channels." in infos
    assert "Ch 2: Antenna repeats the Recording value." in infos
    assert "antenna will be saved as Antenna, the spelling already in use." in infos
    rec = build_recording(form, scan=scan, location=local_location(info))
    assert [(p.param, p.value, p.channel_index) for p in rec.params] == [
        ("Antenna", "Omni", None),
        ("Antenna", "Omni", 0),
        ("Antenna", "LogP", 1),
        ("Antenna", "Omni", 2),
    ]


@pytest.mark.parametrize("scope", [None, 1])
def test_same_scope_with_different_values_is_an_error(make_recording, scope):
    params = [
        ParamInput(param="Antenna", value="Omni", channel_index=scope),
        ParamInput(param="ANTENNA", value="LogP", channel_index=scope),
    ]
    _, _, _, items = rf_items(make_recording, params)
    label = "Recording" if scope is None else "Ch 1"
    assert f"{label}: Antenna has 2 different values (Omni, LogP). Keep one row." in texts(
        items, ItemState.ERROR
    )
    assert not can_save(items)


def test_a_different_unit_is_a_different_value(make_recording):
    params = [
        ParamInput(param="Gain", value="30", unit="dB"),
        ParamInput(param="Gain", value="30", unit="dBm"),
    ]
    _, _, _, items = rf_items(make_recording, params)
    assert "Recording: Gain has 2 different values (30 dB, 30 dBm). Keep one row." in texts(
        items, ItemState.ERROR
    )


def test_same_scope_same_value_is_saved_once(make_recording):
    params = [
        ParamInput(param="Antenna", value="Omni", channel_index=1),
        ParamInput(param="antenna", value=" omni ", channel_index=1),
        ParamInput(param="SDR", value="X310"),
    ]
    form, scan, info, items = rf_items(make_recording, params)
    assert can_save(items)
    assert "Ch 1: Antenna appears 2 times with the same value. It is saved once." in texts(
        items, ItemState.INFO
    )
    rec = build_recording(form, scan=scan, location=local_location(info))
    assert [(p.param, p.value, p.channel_index) for p in rec.params] == [
        ("Antenna", "Omni", 1),
        ("SDR", "X310", None),
    ]


def test_spelling_already_in_the_database_wins(make_recording):
    params = [ParamInput(param="lna GAIN", value="20", unit="dB", channel_index=0)]
    form, scan, info, items = rf_items(make_recording, params, known=["LNA gain"])
    assert "lna GAIN will be saved as LNA gain, the spelling already in use." in texts(
        items, ItemState.INFO
    )
    rec = build_recording(
        form, scan=scan, location=local_location(info), known_param_names=["LNA gain"]
    )
    assert rec.params[0].param == "LNA gain"


def test_a_typo_is_a_separate_parameter(make_recording):
    params = [
        ParamInput(param="Antenna", value="Omni"),
        ParamInput(param="Antena", value="LogP", channel_index=1),
    ]
    _, _, _, items = rf_items(make_recording, params)
    assert can_save(items)
    assert not any("Antena" in t or "Antenna" in t for t in texts(items))


def test_incomplete_rows_are_left_to_the_to_do_items(make_recording):
    params = [
        ParamInput(param="Antenna", value="Omni"),
        ParamInput(param="Antenna", value="", channel_index=1),
    ]
    _, _, _, items = rf_items(make_recording, params)
    assert texts(items, ItemState.TODO) == ["RF chain row 2 (Antenna): enter a value"]
    assert not any("Ch 1: Antenna" in t for t in texts(items))


def test_param_spellings():
    params = [ParamInput(param=" sdr ", value="x"), ParamInput(param="Mixer", value="y")]
    assert entry.param_spellings(params, ["SDR"]) == {"sdr": "SDR", "mixer": "Mixer"}
