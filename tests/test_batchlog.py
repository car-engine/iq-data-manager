"""Tests for iqdm.batchlog: several folders with one set-up (DECISIONS.md D90).

Folders are synthetic recordings under tmp_path; the database is a fresh one.
"""

from dataclasses import replace
from pathlib import Path

import pytest

import make_fixtures
from conftest import recorder_log_text
from iqdm import batchlog, entry
from iqdm.batchlog import BatchFolder, FolderChecks, SaveOutcome
from iqdm.db import repository
from iqdm.db.connection import open_db
from iqdm.entry import ChannelInput, EntryInput, ItemState, ParamInput
from iqdm.location import split_location
from iqdm.models import SampleType
from iqdm.scan.scanner import scan_recording
from make_fixtures import RecordingSpec

T0 = make_fixtures.DEFAULT_START_UNIX


def recording(parent: Path, name: str, *, log=None, start=T0, **kw) -> Path:
    """A synthetic recording `parent/name`, with a recorder log when `log` maps channels."""
    info = make_fixtures.make_recording(parent / name, RecordingSpec(start_unix=start, **kw))
    root = Path(info.root)
    if log is not None:
        (root / f"recorder_{root.name}.log").write_text(recorder_log_text(log), encoding="utf-8")
    return root


def scanned(path: Path, db_path=None, **kw) -> BatchFolder:
    return batchlog.scan_folder(
        BatchFolder(path=str(path)),
        nas_roots=(),
        resolve_drive=None,
        db_path=None if db_path is None else str(db_path),
        **kw,
    )


@pytest.fixture
def site_id(db_path) -> int:
    return entry.add_site(db_path, "SiteA").id


def shared_form(site_id: int | None = None, **kw) -> EntryInput:
    return EntryInput(site_id=site_id, **({"logged_by": "userA"} | kw))


def texts(items, state: ItemState | None = None) -> list[str]:
    return [i.text for i in items if state is None or i.state is state]


# ---------------------------------------------------------------------------
# Choosing folders
# ---------------------------------------------------------------------------


def test_the_recording_folders_of_a_parent_are_listed(tmp_path):
    session = tmp_path / "session"
    recording(session, "b-1100")
    recording(session, "a-1000", n_channels=2)
    (session / "notes").mkdir()
    (session / "notes" / "readme.txt").write_text("x", encoding="utf-8")
    found = batchlog.list_candidates(session)
    assert [p.name for p in found.folders] == ["a-1000", "b-1100"]
    assert not found.parent_is_recording


def test_a_parent_that_is_itself_a_recording(tmp_path):
    root = recording(tmp_path, "rec", n_channels=2)
    found = batchlog.list_candidates(root)
    assert found.folders == ()  # its subfolders 0 and 1 are channel folders
    assert found.parent_is_recording


def test_the_same_folder_compares_without_letter_case():
    assert batchlog.same_folder(r"D:\Rec\a", r"d:\rec\A\.")
    assert not batchlog.same_folder(r"D:\rec\a", r"D:\rec\b")


# ---------------------------------------------------------------------------
# Scanning one folder
# ---------------------------------------------------------------------------


def test_a_scan_takes_fc_fs_band_and_sample_type_from_the_log(tmp_path, db_path):
    root = recording(tmp_path, "rec", n_channels=2, log={0: (145.8, 30.0), 1: (433.0, 30.0)})
    folder = scanned(root, db_path)
    assert folder.scanned and folder.duplicate_checked and folder.logged_id is None
    assert folder.log_dtype is SampleType.INT16
    c0, c1 = folder.channels[0], folder.channels[1]
    assert (c0.fc_mhz, c0.band, c0.fs_text) == ("145.8", "VHF", "1 kHz")
    assert (c1.fc_mhz, c1.band) == ("433", "UHF")
    assert c0.fc_from_log and c0.fs_from_log and c0.band_from_fc
    assert folder.file_duration_s == 1.0


def test_a_scan_without_a_log_leaves_fc_to_the_user(tmp_path):
    folder = scanned(recording(tmp_path, "rec"))
    assert folder.recorder is None
    assert folder.channels[0] == ChannelInput(channel_index=0)


def test_a_folder_that_cannot_be_logged_keeps_its_reason(tmp_path):
    folder = batchlog.scan_folder(
        BatchFolder(path="C:\\"), nas_roots=(), resolve_drive=None, db_path=None
    )
    assert folder.scanned and folder.scan is None
    assert folder.location_error
    view = batchlog.folder_items(shared_form(1), folder, [folder])
    assert any("cannot be logged" in t for t in texts(view.items, ItemState.ERROR))


def test_a_missing_folder_gives_its_scan_problem(tmp_path):
    folder = scanned(tmp_path / "gone")
    assert folder.scan is None
    assert folder.scan_problems
    view = batchlog.folder_items(shared_form(1), folder, [folder])
    assert any(t.startswith("The scan stopped") for t in texts(view.items, ItemState.ERROR))


def test_a_scan_keeps_the_key_and_clears_an_earlier_save_error(tmp_path):
    first = BatchFolder(path=str(recording(tmp_path, "rec")), save_error="locked")
    again = batchlog.scan_folder(first, nas_roots=(), resolve_drive=None, db_path=None)
    assert again.key == first.key
    assert again.save_error is None


# ---------------------------------------------------------------------------
# The form of one folder
# ---------------------------------------------------------------------------


def test_the_logs_values_win_over_the_shared_ones(tmp_path):
    folder = scanned(recording(tmp_path, "rec", log={0: (300.0, 30.0)}))
    shared = shared_form(
        1,
        dtype=SampleType.INT8,
        params=[
            ParamInput(param="Antenna", value="Yagi"),
            ParamInput(param="USRP gain", value="10", unit="dB"),
        ],
    )
    form, values = batchlog.form_for(shared, folder)
    assert form.dtype is SampleType.INT16  # the log's sc16
    assert [(p.param, p.value) for p in form.params] == [
        ("Antenna", "Yagi"),
        ("USRP gain", "30"),
        ("Clock reference", "GPSDO"),
        ("USRP", "X310 + UBX"),
    ]
    assert form.logged_by == "userA"
    assert values is not None and values.dtype is SampleType.INT16


def test_the_log_rows_shown_are_the_ones_saved(tmp_path):
    """O55: what the screen lists is what form_for() puts into the entry."""
    folder = scanned(recording(tmp_path, "rec", log={0: (300.0, 30.0)}))
    shared = shared_form(
        1,
        dtype=SampleType.INT8,
        params=[
            ParamInput(param="Antenna", value="Yagi"),
            ParamInput(param="USRP gain", value="10", unit="dB"),
        ],
    )
    shown = batchlog.log_shown(shared, folder)
    assert shown is not None
    form, _ = batchlog.form_for(shared, folder)
    assert [p for p in form.params if p not in shared.params] == list(shown.rows)
    assert [(p.param, p.value, p.unit) for p in shown.rows] == [
        ("USRP gain", "30", "dB"),
        ("Clock reference", "GPSDO", ""),
        ("USRP", "X310 + UBX", ""),
    ]
    assert shown.replaced == (ParamInput(param="USRP gain", value="10", unit="dB"),)
    assert shown.dtype is SampleType.INT16


def test_a_shared_usrp_row_stays_and_is_not_shown_as_replaced(tmp_path):
    folder = scanned(recording(tmp_path, "rec", log={0: (300.0, 30.0)}))
    shared = shared_form(1, params=[ParamInput(param="USRP", value="USRP-2954")])
    shown = batchlog.log_shown(shared, folder)
    assert shown is not None
    assert "USRP" not in [p.param for p in shown.rows]  # D82: the form's own USRP row stays
    assert shown.replaced == ()


def test_no_log_rows_without_a_log(tmp_path):
    assert batchlog.log_shown(shared_form(1), scanned(recording(tmp_path, "rec"))) is None
    assert batchlog.log_shown(shared_form(1), BatchFolder(path=str(tmp_path))) is None


def test_fs_follows_the_shared_format_without_a_log(tmp_path):
    folder = scanned(recording(tmp_path, "rec", header_bytes=0))
    form, _ = batchlog.form_for(shared_form(1), folder)
    assert form.channels[0].fs_text == "1 kHz"
    assert form.channels[0].fs_inferred
    form, _ = batchlog.form_for(shared_form(1, dtype=SampleType.INT8), folder)
    assert form.channels[0].fs_text == "2 kHz"  # the same files read as int8


def test_a_typed_fs_stays(tmp_path):
    folder = scanned(recording(tmp_path, "rec"))
    folder.channels[0] = ChannelInput(channel_index=0, fc_mhz="433", fs_text="1k")
    form, _ = batchlog.form_for(shared_form(1, dtype=SampleType.INT8), folder)
    assert form.channels[0].fs_text == "1k"
    assert not form.channels[0].fs_inferred


def test_the_file_duration_comes_from_each_folders_names(tmp_path):
    folder = scanned(recording(tmp_path, "rec", file_duration_s=2.0, log={0: (300.0, 30.0)}))
    assert (folder.file_duration_s, folder.duration_inferred) == (2.0, True)
    form, _ = batchlog.form_for(shared_form(1), folder)
    assert form.file_duration_s == 2.0


# ---------------------------------------------------------------------------
# Checklists
# ---------------------------------------------------------------------------


def test_a_ready_folder(tmp_path, site_id, db_path):
    folder = scanned(recording(tmp_path, "rec", log={0: (300.0, 30.0)}), db_path)
    view = batchlog.folder_items(shared_form(site_id), folder, [folder])
    assert texts(view.items, ItemState.ERROR) == []
    assert texts(view.items, ItemState.TODO) == []
    assert batchlog.is_ready(folder, view.items)
    assert batchlog.folder_state(folder, view.items)[0] in (ItemState.OK, ItemState.INFO)


def test_an_already_logged_folder_is_an_error(tmp_path, site_id, db_path):
    root = recording(tmp_path, "rec", log={0: (300.0, 30.0)})
    first = scanned(root, db_path)
    view = batchlog.folder_items(shared_form(site_id), first, [first])
    built, _ = batchlog.build_recordings([(first, view)])
    entry.save_new(db_path, built[0][1])
    again = scanned(root, db_path)
    assert again.logged_id == 1
    view = batchlog.folder_items(shared_form(site_id), again, [again])
    assert "Folder already logged as recording 1" in texts(view.items, ItemState.ERROR)
    assert batchlog.folder_state(again, view.items) == (ItemState.ERROR, "1 error")


def test_the_same_capture_twice_in_the_list(tmp_path):
    a = scanned(recording(tmp_path, "a", log={0: (300.0, 30.0)}))
    b = scanned(recording(tmp_path, "b", log={0: (300.0, 30.0)}))
    c = scanned(recording(tmp_path, "c", start=T0 + 3600, log={0: (300.0, 30.0)}))
    view = batchlog.folder_items(shared_form(1), a, [a, b, c])
    assert (
        "b in this list has the same start, end and channels. It may be the same capture in "
        "another folder." in texts(view.items, ItemState.INFO)
    )
    assert batchlog.same_capture_in_list(c, [a, b, c]) == []


def test_the_list_checklist_names_a_shared_to_do_once(tmp_path, db_path):
    a = scanned(recording(tmp_path, "a", log={0: (300.0, 30.0)}), db_path)
    b = scanned(recording(tmp_path, "b", start=T0 + 3600), db_path)  # no log: fc to type
    shared = shared_form(None)
    views = [(f, batchlog.folder_items(shared, f, [a, b])) for f in (a, b)]
    items = batchlog.combined_items(views)
    assert texts(items) == [
        "0 of 2 ticked folders ready to save",
        "Choose a site (all 2 folders)",
        "b: Enter fc (MHz) for channel 0",
    ]
    assert items[0].state is ItemState.INFO


def test_the_list_checklist_with_nothing_to_save(tmp_path):
    assert texts(batchlog.combined_items([])) == ["Add folders, then scan them"]
    a = scanned(recording(tmp_path, "a"))
    a.ticked = False
    view = batchlog.folder_items(shared_form(1), a, [a])
    assert texts(batchlog.combined_items([(a, view)])) == ["Tick at least one folder to save"]
    unscanned = BatchFolder(path=str(tmp_path / "b"))
    view = batchlog.folder_items(shared_form(1), unscanned, [unscanned])
    assert texts(batchlog.combined_items([(unscanned, view)]))[0] == (
        "Scan the folders: 1 not scanned yet"
    )
    assert batchlog.folder_state(unscanned, view.items) == (ItemState.TODO, "Not scanned")


def test_the_cache_skips_remarks_and_plan_reference(tmp_path, monkeypatch):
    folder = scanned(recording(tmp_path, "rec", log={0: (300.0, 30.0)}))
    calls = []
    real = batchlog.folder_items
    monkeypatch.setattr(
        batchlog, "folder_items", lambda *a, **kw: calls.append(1) or real(*a, **kw)
    )
    checks = FolderChecks()
    checks.view(shared_form(1), folder, [folder])
    view = checks.view(
        shared_form(1, remarks="Hilltop", recording_plan_ref="P-7"), folder, [folder]
    )
    assert len(calls) == 1
    assert (view.form.remarks, view.form.recording_plan_ref) == ("Hilltop", "P-7")
    checks.view(shared_form(1, logged_by="userB"), folder, [folder])
    folder.channels[0] = replace(folder.channels[0], fc_mhz="301")
    checks.view(shared_form(1, logged_by="userB"), folder, [folder])
    assert len(calls) == 3


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


def ready_views(tmp_path, site_id, db_path, names=("a", "b", "c")):
    folders = [
        scanned(recording(tmp_path, n, start=T0 + 3600 * i, log={0: (300.0 + i, 30.0)}), db_path)
        for i, n in enumerate(names)
    ]
    shared = shared_form(site_id, params=[ParamInput(param="Antenna", value="Yagi")])
    return [(f, batchlog.folder_items(shared, f, folders)) for f in folders]


def test_each_folder_is_saved_as_its_own_entry(tmp_path, site_id, db_path):
    views = ready_views(tmp_path, site_id, db_path)
    built, failed = batchlog.build_recordings(views)
    assert failed == [] and len(built) == 3
    progress = []
    outcomes = batchlog.save_all(str(db_path), built, progress=progress.append)
    assert [o.recording_id for o in outcomes] == [1, 2, 3]
    assert progress == [(0, 3), (1, 3), (2, 3)]
    with open_db(db_path, readonly=True) as conn:
        rec = repository.get_recording(conn, 2)
    assert rec.channels[0].fc_hz == 301e6
    assert rec.channels[0].band == "UHF"
    assert {(p.param, p.value) for p in rec.params} >= {("Antenna", "Yagi"), ("USRP gain", "30")}
    assert rec.site_id == site_id


def test_a_folder_logged_meanwhile_is_reported_and_the_rest_saved(tmp_path, site_id, db_path):
    views = ready_views(tmp_path, site_id, db_path)
    built, _ = batchlog.build_recordings(views)
    entry.save_new(db_path, built[1][1])  # another PC logs folder b first
    outcomes = batchlog.save_all(str(db_path), built)
    assert [o.recording_id is not None for o in outcomes] == [True, False, True]
    assert outcomes[1].error
    names = {f.key: f.name for f, _ in views}
    state, text = batchlog.saved_text(outcomes, names)
    assert state is ItemState.INFO
    assert text.startswith("Saved 2 entries (recordings 2 to 3). 1 not saved: b: ")
    assert text.endswith("is already logged")


def test_cancel_stops_between_two_entries(tmp_path, site_id, db_path):
    built, _ = batchlog.build_recordings(ready_views(tmp_path, site_id, db_path))
    seen = []

    def cancelled() -> bool:
        return len(seen) >= 1

    outcomes = batchlog.save_all(
        str(db_path), built, cancelled=cancelled, save=lambda db, rec: seen.append(rec) or 9
    )
    assert len(outcomes) == 1


def test_unticked_and_unready_folders_are_not_built(tmp_path, site_id, db_path):
    views = ready_views(tmp_path, site_id, db_path)
    views[0][0].ticked = False
    views[2][0].saved_id = 7
    built, failed = batchlog.build_recordings(views)
    assert [key for key, _ in built] == [views[1][0].key]
    assert failed == []


def test_the_save_question(tmp_path, site_id, db_path):
    views = ready_views(tmp_path, site_id, db_path)
    views[2][0].ticked = False
    question = batchlog.save_question(
        views, site="SiteA", project="", logged_by="userA", offset_hours=8.0
    )
    assert question.startswith("Save 2 entries?\n\n")
    assert "Site: SiteA. Project: none. Logged by: userA." in question
    assert "From 2026-09-30 10:00:00 to 2026-09-30 11:00:10 UTC+8, 80.0 kB in total." in question
    assert "Not saved now, unticked or not ready: c." in question


def test_the_saved_text():
    names = {1: "a", 2: "b"}
    assert batchlog.saved_text([SaveOutcome(1, recording_id=5)], names) == (
        ItemState.OK,
        "Saved 1 entry (recording 5).",
    )
    assert batchlog.saved_text(
        [SaveOutcome(1, recording_id=5), SaveOutcome(2, recording_id=6)], names
    ) == (ItemState.OK, "Saved 2 entries (recordings 5 to 6).")
    assert batchlog.saved_text([SaveOutcome(2, error="locked")], names) == (
        ItemState.ERROR,
        "1 not saved: b: locked",
    )
    assert batchlog.saved_text([], names) == (ItemState.INFO, "Nothing saved.")


def test_the_scan_result_matches_the_one_folder_form(tmp_path, db_path, site_id):
    """The checklist of a folder equals the one-folder form's for the same input."""
    root = recording(tmp_path, "rec")
    folder = scanned(root, db_path)
    folder.channels[0] = ChannelInput(channel_index=0, fc_mhz="433", band="UHF")
    view = batchlog.folder_items(shared_form(site_id), folder, [folder])
    scan = scan_recording(root, 1.0)
    form = shared_form(
        site_id,
        channels=[
            ChannelInput(
                channel_index=0, fc_mhz="433", band="UHF", fs_text="1 kHz", fs_inferred=True
            )
        ],
    )
    one = entry.checklist(
        form, scan=scan, location=split_location(str(root)), duplicate_checked=True
    )
    assert texts(view.items) == texts(one)
