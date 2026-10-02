"""Tests for iqdm.entry: form input, checklist and saving. Data lives in tmp_path."""

import math
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
    SampleType,
    Verification,
)
from iqdm.scan.scanner import ChannelScan, DataFile, ScanResult, scan_recording
from make_fixtures import ChannelSpec

T0 = 1790733600  # 2026-09-30T02:00:00Z
FS_MHZ = "0.001"  # make_fixtures default: 1 kS/s, int16, 4000 bytes per 1 s file
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
            ChannelInput(channel_index=c.channel_index, band="VHF", fc_mhz="145.8", fs_mhz=FS_MHZ)
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


def test_not_scanned_is_an_error():
    items = checklist(EntryInput(logged_by="u", site_id=1), scan=None)
    assert "Folder not scanned" in texts(items, ItemState.ERROR)
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
    form.channels[0].fs_mhz = "0.002"
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
    form.channels[0].fs_mhz = "0.0010005"
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
    form.channels[1].fs_mhz = "0.002"
    items = ready_items(form, scan, split_location(str(tmp_path / "rec")))
    assert can_save(items)
    assert f"File sizes match fs {TIMES} 4 bytes in every channel" in texts(items, ItemState.OK)


def test_gaps_are_information(make_recording):
    info = make_recording(n_channels=2, channels={1: ChannelSpec(gaps=frozenset({3, 4, 5}))})
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    assert can_save(items)
    assert "Channel 1 has 3 missing seconds in 1 gap. Gaps are information only." in texts(
        items, ItemState.INFO
    )


def test_unrecognised_entries_are_information(make_recording):
    info = make_recording(junk=True)
    scan = scan_of(info)
    items = ready_items(form_for(scan, 1), scan, local_location(info))
    assert can_save(items)
    (line,) = [t for t in texts(items, ItemState.INFO) if "not recognised" in t]
    assert line.startswith(f"{len(scan.unrecognised)} entries not recognised and ignored: ")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"logged_by": "  "}, "Logged by is empty"),
        ({"site_id": None}, "No site chosen"),
        ({"file_duration_s": 0.0}, "File duration must be positive"),
        ({"header_bytes": -1}, "Header bytes must be 0 or more"),
    ],
)
def test_missing_required_field(make_recording, change, message):
    info = make_recording()
    scan = scan_of(info)
    form = form_for(scan, 1)
    for name, value in change.items():
        setattr(form, name, value)
    items = ready_items(form, scan, local_location(info))
    assert message in texts(items, ItemState.ERROR)
    assert "Required fields filled" not in texts(items)


@pytest.mark.parametrize(
    ("field", "text", "message"),
    [
        ("fc_mhz", "", "Channel 0: fc (MHz) is empty"),
        ("fc_mhz", "-1", "Channel 0: fc (MHz) must be positive: '-1'"),
        ("fs_mhz", "x", "Channel 0: fs (MHz) is not a number: 'x'"),
        ("fs_mhz", "0", "Channel 0: fs (MHz) must be positive: '0'"),
    ],
)
def test_channel_frequencies_are_required_and_positive(make_recording, field, text, message):
    info = make_recording()
    scan = scan_of(info)
    form = form_for(scan, 1)
    setattr(form.channels[0], field, text)
    items = ready_items(form, scan, local_location(info))
    assert message in texts(items, ItemState.ERROR)


def test_channel_without_input_row_is_reported(make_recording):
    info = make_recording(n_channels=2)
    scan = scan_of(info)
    form = form_for(scan, 1)
    form.channels.pop()
    items = ready_items(form, scan, local_location(info))
    assert "Channel 1: fc (MHz) is empty" in texts(items, ItemState.ERROR)


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
    assert texts(items, ItemState.ERROR) == [
        "RF chain row 3: the parameter name is empty",
        "RF chain row 4 (Antenna): the value is empty",
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
        channel_index=0, band="VHF", fc_mhz="145.8", fs_mhz="0.001"
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
        lambda f: setattr(f.channels[0], "fs_mhz", "0.002"),
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
    assert "Channel 1: fs (MHz) is empty" in texts(items, ItemState.ERROR)


def test_save_edit_needs_an_id(make_recording, db_path):
    info = make_recording()
    scan = scan_of(info)
    rec = build_recording(form_for(scan, 1), scan=scan, location=local_location(info))
    with pytest.raises(ValueError, match=r"rec\.id"):
        save_edit(db_path, rec)


def test_state_note():
    local = Location(storage_root="E:\\", rel_path="r", archive_state=ArchiveState.LOCAL)
    nas = Location(storage_root=NAS, rel_path="r", archive_state=ArchiveState.ARCHIVED)
    assert entry.state_note(local, None).startswith("Saved with state local.")
    assert entry.state_note(nas, None).startswith("Saved with state archived.")
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
