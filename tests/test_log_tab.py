"""GUI tests for the Log tab (pytest-qt, offscreen). Data lives in tmp_path.

The tab runs its database and scan work on a thread pool. Each test waits for the
tab's TaskRunner to be idle before it checks results.
"""

import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from iqdm import entry
from iqdm.config import Config
from iqdm.db import repository
from iqdm.db.connection import DatabaseBusyError, open_db
from iqdm.entry import ItemState
from iqdm.gui.log_tab import LogTab, scan_summary, utc_text
from iqdm.gui.workers import TaskRunner
from iqdm.location import split_location
from iqdm.models import ArchiveState, Operation, SampleType
from iqdm.scan.scanner import ScanCancelled, scan_recording
from make_fixtures import ChannelSpec

NAS = r"\\nas\recordings"


def wait_idle(qtbot, tab: LogTab) -> None:
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)


@pytest.fixture
def site_id(db_path) -> int:
    return entry.add_site(db_path, "SiteA").id


@pytest.fixture
def make_tab(qtbot, db_path):
    tabs: list[LogTab] = []

    def _make(config: Config | None = None, **kw) -> LogTab:
        tab = LogTab(Config(db_path=str(db_path)) if config is None else config, **kw)
        qtbot.addWidget(tab)
        tabs.append(tab)
        wait_idle(qtbot, tab)
        return tab

    yield _make
    for tab in tabs:
        tab.cancel_scan()
        tab.runner.wait(10_000)


def scan_folder(qtbot, tab: LogTab, folder: str) -> None:
    tab.folder_edit.setText(folder)
    tab.start_scan()
    wait_idle(qtbot, tab)


def fill_channels(tab: LogTab, fs_mhz: str = "0.001", fc_mhz: str = "145.8") -> None:
    for c in tab.current_input().channels:
        band, fc, fs = tab.channel_widgets(c.channel_index)
        band.setCurrentText("VHF")
        fc.setText(fc_mhz)
        fs.setText(fs_mhz)


def choose_site(tab: LogTab, site_id: int) -> None:
    tab.site_combo.setCurrentIndex(tab.site_combo.findData(site_id))


def checklist_texts(tab: LogTab, state: ItemState | None = None) -> list[str]:
    tab.refresh_checklist()
    return [i.text for i in tab.checklist.items if state is None or i.state is state]


def logged_ready(qtbot, tab: LogTab, info, site_id: int) -> None:
    scan_folder(qtbot, tab, info.root)
    fill_channels(tab)
    choose_site(tab, site_id)
    tab.logged_by_edit.setText("userA")
    tab.refresh_checklist()


def save_and_wait(qtbot, tab: LogTab) -> None:
    tab.save()
    wait_idle(qtbot, tab)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_without_database_save_is_disabled(qtbot):
    tab = LogTab(Config())
    qtbot.addWidget(tab)
    assert not tab.runner.busy
    assert "No database configured" in tab.message_label.text()
    assert not tab.save_button.isEnabled()
    assert tab.mode_label.text() == "New entry"
    assert "Scan the folder" in checklist_texts(tab, ItemState.TODO)


def test_loads_sites_parameter_names_and_bands(make_tab, db_path, site_id, make_recording):
    info = make_recording()
    scan = scan_recording(Path(info.root), 1.0)
    form = entry.EntryInput(
        logged_by="u",
        site_id=site_id,
        channels=[entry.ChannelInput(channel_index=0, band="UHF", fc_mhz="400", fs_mhz="0.001")],
        params=[entry.ParamInput(param="SDR", value="X310")],
    )
    location = split_location(info.root)
    entry.save_new(db_path, entry.build_recording(form, scan=scan, location=location))
    entry.add_site(db_path, "Alpha")

    tab = make_tab()
    sites = [tab.site_combo.itemText(i) for i in range(tab.site_combo.count())]
    assert sites == ["Alpha", "SiteA"]
    assert tab.site_combo.currentIndex() == -1
    assert tab._choices.param_names == ["SDR"]
    assert tab._choices.bands == ["UHF"]


def test_logged_by_defaults_to_the_login_name(make_tab, monkeypatch):
    monkeypatch.setattr("iqdm.entry.getpass.getuser", lambda: "userA")
    tab = make_tab()
    assert tab.logged_by_edit.text() == "userA"


def test_database_that_cannot_be_read_is_reported(make_tab, tmp_path):
    tab = make_tab(Config(db_path=str(tmp_path / "missing.db")))
    assert "Cannot read the database" in tab.message_label.text()


# ---------------------------------------------------------------------------
# Folder and scan
# ---------------------------------------------------------------------------


def test_folder_gives_storage_root_and_relative_path(make_tab, make_recording):
    info = make_recording()
    tab = make_tab()
    tab.folder_edit.setText(info.root)
    root = Path(info.root)
    assert Path(tab.storage_root_edit.text()) == root.parent
    assert tab.rel_path_edit.text() == root.name
    assert tab.state_edit.text() == "local"


def test_folder_under_a_mapped_nas_drive_is_archived(make_tab, make_recording, db_path):
    info = make_recording()
    drive = Path(info.root).drive
    tab = make_tab(
        Config(db_path=str(db_path), nas_roots=(NAS,)),
        resolve_drive=lambda d: NAS if d == drive.upper() else None,
    )
    tab.folder_edit.setText(info.root)
    assert tab.storage_root_edit.text() == NAS
    assert tab.state_edit.text() == "archived"
    assert tab.state_note.text().startswith("Saved with state archived.")


def test_drive_root_cannot_be_logged(make_tab, tmp_path):
    tab = make_tab()
    tab.folder_edit.setText(Path(tmp_path).anchor)
    errors = checklist_texts(tab, ItemState.ERROR)
    assert any(t.startswith("Folder cannot be logged: a drive or share root") for t in errors)
    tab.start_scan()
    assert not tab.runner.busy
    assert tab.message_label.text().startswith("Folder cannot be logged")


def test_scan_fills_channel_table_and_times(qtbot, make_tab, make_recording):
    info = make_recording(n_channels=2, n_slots=10, channels={1: ChannelSpec(gaps=frozenset({3}))})
    tab = make_tab()
    tab.folder_edit.setText(info.root)
    tab.start_scan()
    assert tab.scan_summary.text().startswith("Scanning")
    wait_idle(qtbot, tab)
    assert tab.scan is not None
    assert tab.channel_table.rowCount() == 2
    assert [tab.channel_table.item(r, 0).text() for r in range(2)] == ["0", "1"]
    assert tab.channel_table.item(0, 1).text() == "0"
    assert tab.channel_table.item(0, 5).text() == "2026-09-30 02:00:00"
    assert tab.channel_table.item(0, 6).text() == "2026-09-30 02:00:10"
    assert tab.channel_table.item(0, 7).text() == "10"
    assert tab.channel_table.item(0, 8).text() == "100.0%"
    assert tab.channel_table.item(1, 7).text() == "9"
    assert tab.channel_table.item(1, 8).text() == "90.0%"
    assert tab.start_edit.text() == "2026-09-30 02:00:00"
    assert tab.end_edit.text() == "2026-09-30 02:00:10"
    summary = tab.scan_summary.text()
    assert summary.startswith("Found channel folders 0 and 1 · 19 files")
    assert "2026-09-30 02:00:00 to 2026-09-30 02:00:10 UTC" in summary
    assert "ch 1 has 1 missing second" in summary
    assert "Folder not already in the database" in checklist_texts(tab, ItemState.OK)


def test_scan_reports_progress_and_can_be_cancelled(qtbot, make_tab, make_recording, monkeypatch):
    info = make_recording(n_slots=5)
    tab = make_tab()
    calls: list[int] = []

    def slow_scan(folder, duration, *, progress, cancelled):
        progress(1000)
        while not cancelled():
            time.sleep(0.01)
        calls.append(1)
        raise ScanCancelled

    monkeypatch.setattr("iqdm.gui.log_tab.scan_recording", slow_scan)
    tab.folder_edit.setText(info.root)
    tab.start_scan()
    qtbot.waitUntil(lambda: "1,000 files found" in tab.scan_summary.text(), timeout=5000)
    assert tab.cancel_button.isEnabled()
    assert not tab.scan_button.isEnabled()
    assert not tab.save_button.isEnabled()
    tab.cancel_scan()
    wait_idle(qtbot, tab)
    assert calls == [1]
    assert tab.scan_summary.text() == "Scan cancelled."
    assert tab.scan is None
    assert tab.channel_table.rowCount() == 0
    assert tab.scan_button.isEnabled()


def test_scan_error_lists_the_problems(qtbot, make_tab, make_recording):
    info = make_recording(n_channels=1)
    Path(info.root, "01").mkdir()
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    assert tab.scan_summary.text().startswith("Scan stopped:")
    assert "leading zero: 01" in tab.scan_summary.text()
    assert tab.scan is None
    assert checklist_texts(tab, ItemState.ERROR) == [
        "The scan stopped with 1 problem. Fix the folder and scan again: "
        "channel folder name has a leading zero: 01"
    ]
    tab.folder_edit.setText(info.root + "x")
    assert "Scan the folder" in checklist_texts(tab, ItemState.TODO)
    assert not tab.save_button.isEnabled()


def test_changing_the_folder_drops_the_scan(qtbot, make_tab, make_recording):
    first, second = make_recording(), make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, first.root)
    assert tab.scan is not None
    tab.folder_edit.setText(second.root)
    assert tab.scan is None
    assert tab.channel_table.rowCount() == 0


def test_duration_change_updates_times_without_a_rescan(qtbot, make_tab, make_recording):
    info = make_recording(n_slots=10)
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    tab.duration_spin.setValue(2.0)
    assert tab.scan.file_duration_s == 2.0
    assert tab.end_edit.text() == "2026-09-30 02:00:11"
    fill_channels(tab)
    errors = checklist_texts(tab, ItemState.ERROR)
    assert any("expected size of 8000 bytes" in t for t in errors)


# ---------------------------------------------------------------------------
# Saving a new entry
# ---------------------------------------------------------------------------


def test_save_writes_the_recording(qtbot, make_tab, make_recording, db_path, site_id):
    info = make_recording(n_channels=2)
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    tab.plan_edit.setText("plan-7")
    tab.remarks_edit.setPlainText("first test")
    tab.param_table.add_row()
    applies_to, name, value, unit = tab.param_table.row_widgets(0)
    applies_to.setCurrentIndex(applies_to.findData(1))
    name.setText("Gain")
    value.setText("30")
    unit.setText("dB")
    assert entry.can_save(tab.checklist.items), checklist_texts(tab)
    assert tab.save_button.isEnabled()

    save_and_wait(qtbot, tab)
    assert tab.message_label.text() == "Saved as recording 1."
    rec = entry.load_recording(db_path, 1)
    assert rec.logged_by == "userA"
    assert rec.site_id == site_id
    assert rec.recording_plan_ref == "plan-7"
    assert rec.remarks == "first test"
    assert [c.fc_hz for c in rec.channels] == [145_800_000.0, 145_800_000.0]
    assert [(p.param, p.value, p.unit, p.channel_index) for p in rec.params] == [
        ("Gain", "30", "dB", 1)
    ]
    assert rec.archive_state is ArchiveState.LOCAL

    # The same folder is now logged: saving again is refused and editing is offered.
    assert "Folder already logged as recording 1" in checklist_texts(tab, ItemState.ERROR)
    assert not tab.save_button.isEnabled()
    assert tab.edit_existing_button.isVisibleTo(tab)


def test_save_on_the_nas_writes_the_d2_row(qtbot, make_tab, make_recording, db_path, site_id):
    info = make_recording()
    drive = Path(info.root).drive
    tab = make_tab(
        Config(db_path=str(db_path), nas_roots=(NAS,)),
        resolve_drive=lambda d: NAS if d == drive.upper() else None,
    )
    logged_ready(qtbot, tab, info, site_id)
    save_and_wait(qtbot, tab)
    rec = entry.load_recording(db_path, 1)
    assert rec.storage_root == NAS
    assert rec.archive_state is ArchiveState.ARCHIVED
    with open_db(db_path, readonly=True) as conn:
        (row,) = repository.list_transfers(conn, 1)
    assert row.operation is Operation.CHECK
    assert row.notes == "logged in place, not verified against a source"


def test_save_needs_a_clean_checklist(qtbot, make_tab, make_recording, site_id, db_path):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    tab.channel_widgets(0)[2].setText("")
    tab.save()
    assert not tab.runner.busy
    assert tab.message_label.text() == "Complete or fix the items in the checklist first."
    assert entry.find_logged(db_path, tab._location) is None


def test_save_failure_is_reported(qtbot, make_tab, make_recording, site_id, monkeypatch):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)

    def busy(db, rec):
        raise DatabaseBusyError("The database is in use by someone else.")

    monkeypatch.setattr("iqdm.entry.save_new", busy)
    save_and_wait(qtbot, tab)
    assert tab.message_label.text() == "Not saved: The database is in use by someone else."
    assert tab.save_button.isEnabled()


def test_add_site(qtbot, make_tab, monkeypatch, db_path):
    tab = make_tab()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("  New site ", True))
    tab.add_site()
    wait_idle(qtbot, tab)
    qtbot.waitUntil(lambda: tab.site_combo.count() == 1)
    wait_idle(qtbot, tab)
    assert tab.site_combo.currentText() == "New site"
    assert tab.message_label.text() == "Added site New site."


def test_add_duplicate_site_is_reported(qtbot, make_tab, monkeypatch, site_id):
    tab = make_tab()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("sitea", True))
    tab.add_site()
    wait_idle(qtbot, tab)
    assert tab.message_label.text().startswith("Site not added:")


def test_clear_form_resets_every_field(qtbot, make_tab, make_recording, site_id, monkeypatch):
    monkeypatch.setattr("iqdm.entry.getpass.getuser", lambda: "userA")
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    tab.logged_by_edit.setText("someone")
    tab.plan_edit.setText("plan")
    tab.remarks_edit.setPlainText("text")
    tab.duration_spin.setValue(2.0)
    tab.header_spin.setValue(16)
    tab.param_table.add_row()
    tab.clear_form()
    assert tab.folder_edit.text() == ""
    assert tab.scan is None
    assert tab.channel_table.rowCount() == 0
    assert tab.param_table.rows() == []
    assert tab.logged_by_edit.text() == "userA"
    assert (tab.plan_edit.text(), tab.remarks_edit.toPlainText()) == ("", "")
    assert tab.duration_spin.value() == 1.0
    assert tab.header_spin.value() == 0
    assert tab.site_combo.currentIndex() == -1
    assert tab.storage_root_edit.text() == ""
    assert tab.mode_label.text() == "New entry"


# ---------------------------------------------------------------------------
# Edit mode (DECISIONS.md D16)
# ---------------------------------------------------------------------------


def saved_tab(qtbot, make_tab, info, site_id) -> LogTab:
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    tab.param_table.add_row(entry.ParamInput(param="Gain", value="30", channel_index=1))
    save_and_wait(qtbot, tab)
    assert tab.message_label.text() == "Saved as recording 1.", checklist_texts(tab)
    return tab


def test_edit_existing_entry_opens_edit_mode(qtbot, make_tab, make_recording, site_id):
    info = make_recording(n_channels=2)
    tab = saved_tab(qtbot, make_tab, info, site_id)
    tab.edit_existing_button.click()
    wait_idle(qtbot, tab)
    assert tab.editing is not None
    assert tab.mode_label.text() == "Editing recording 1"
    assert tab.folder_edit.isReadOnly()
    assert not tab.browse_button.isEnabled()
    assert Path(tab.folder_edit.text()) == Path(info.root)
    assert tab.channel_table.rowCount() == 2
    assert tab.channel_widgets(0)[1].text() == "145.8"
    assert tab.site_combo.currentData() == site_id
    assert [p.param for p in tab.param_table.rows()] == ["Gain"]
    assert "Not rescanned: the stored file counts and times are kept" in checklist_texts(
        tab, ItemState.INFO
    )
    assert tab.save_button.isEnabled()


def test_edit_metadata_and_save(qtbot, make_tab, make_recording, site_id, db_path):
    info = make_recording(n_channels=2)
    tab = saved_tab(qtbot, make_tab, info, site_id)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    tab.remarks_edit.setPlainText("edited")
    tab.channel_widgets(1)[1].setText("433.92")
    save_and_wait(qtbot, tab)
    assert tab.message_label.text() == "Saved changes to recording 1."
    rec = entry.load_recording(db_path, 1)
    assert rec.remarks == "edited"
    assert rec.channels[1].fc_hz == 433_920_000.0
    assert tab.editing is not None
    assert tab.editing.remarks == "edited"


def test_edit_of_fs_needs_a_rescan(qtbot, make_tab, make_recording, site_id):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    tab.channel_widgets(0)[2].setText("0.002")
    assert any("scan the folder again" in t for t in checklist_texts(tab, ItemState.ERROR))
    assert not tab.save_button.isEnabled()


def remove_channel_folder_by_moving(info) -> None:
    """Hide channel 1 from the scanner by renaming its folder (no file is deleted)."""
    Path(info.root, "1").rename(Path(info.root, "hidden_1"))


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
def test_rescan_that_removes_a_channel_asks_first(
    qtbot, make_tab, make_recording, site_id, db_path, monkeypatch, answer
):
    info = make_recording(n_channels=2)
    tab = saved_tab(qtbot, make_tab, info, site_id)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    remove_channel_folder_by_moving(info)
    tab.start_scan()
    wait_idle(qtbot, tab)
    assert tab.channel_table.rowCount() == 1
    infos = checklist_texts(tab, ItemState.INFO)
    assert "The rescan removes channel 1 and 1 parameter. Saving asks for confirmation." in infos
    # D20: the Gain row on channel 1 left the form with the rescan.
    assert tab.param_table.rows() == []
    assert tab.message_label.text() == (
        "The rescan no longer finds channel 1. 1 RF chain row of that channel was removed "
        "from the form. Saving asks for confirmation."
    )
    assert checklist_texts(tab, ItemState.ERROR) == []
    assert tab.save_button.isEnabled()

    questions: list[str] = []

    def question(parent, title, text, *args):
        questions.append(text)
        return answer

    monkeypatch.setattr(QMessageBox, "question", question)
    save_and_wait(qtbot, tab)
    assert len(questions) == 1
    assert "channel 1" in questions[0]
    assert "with 1 RF chain parameter." in questions[0]
    rec = entry.load_recording(db_path, 1)
    if answer == QMessageBox.StandardButton.No:
        assert tab.message_label.text() == (
            "Nothing saved. The channels and their RF chain rows stay in the database. "
            "Open the entry again to see the stored rows."
        )
        assert [c.channel_index for c in rec.channels] == [0, 1]
        assert len(rec.params) == 1
    else:
        assert tab.message_label.text() == "Saved changes to recording 1."
        assert [c.channel_index for c in rec.channels] == [0]
        assert rec.params == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_utc_text():
    assert utc_text(1790733600.0) == "2026-09-30 02:00:00"
    assert utc_text(None) == ""


def test_scan_summary_for_a_flat_folder(make_recording):
    info = make_recording(flat=True, n_slots=3)
    text = scan_summary(scan_recording(Path(info.root), 1.0))
    assert text.startswith("Found data files in the recording folder · 3 files · 12.0 kB · ")


def test_task_runner_delivers_results_and_errors(qtbot):
    runner = TaskRunner()
    results: list[object] = []
    runner.start(lambda task: 42, on_success=results.append)
    runner.start(lambda task: 1 / 0, on_failure=results.append)
    qtbot.waitUntil(lambda: not runner.busy, timeout=5000)
    assert 42 in results
    assert any(isinstance(r, ZeroDivisionError) for r in results)


def test_rescan_keeps_rows_of_the_recording_and_other_channels(
    qtbot, make_tab, make_recording, site_id
):
    info = make_recording(n_channels=2)
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    for p in (
        entry.ParamInput(param="SDR", value="X310"),
        entry.ParamInput(param="Gain", value="30", channel_index=1),
        entry.ParamInput(param="LNA", value="on", channel_index=0),
    ):
        tab.param_table.add_row(p)
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    remove_channel_folder_by_moving(info)
    tab.start_scan()
    wait_idle(qtbot, tab)
    assert [(p.param, p.channel_index) for p in tab.param_table.rows()] == [
        ("SDR", None),
        ("LNA", 0),
    ]


def test_rescan_without_a_removed_channel_keeps_every_row(qtbot, make_tab, make_recording, site_id):
    info = make_recording(n_channels=2)
    tab = saved_tab(qtbot, make_tab, info, site_id)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    tab.start_scan()
    wait_idle(qtbot, tab)
    assert [p.param for p in tab.param_table.rows()] == ["Gain"]
    assert tab.message_label.text() == ""


# ---------------------------------------------------------------------------
# fs from the file size (D21), duration from the file names (D22), to-do items (D23)
# ---------------------------------------------------------------------------


def fs_widget(tab: LogTab, index: int = 0):
    return tab.channel_widgets(index)[2]


def test_scan_fills_in_fs_and_leaves_fc_and_site_to_do(qtbot, make_tab, make_recording):
    info = make_recording(n_channels=4)
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    for index in range(4):
        fs = fs_widget(tab, index)
        assert fs.text() == "0.001"
        assert "italic" in fs.styleSheet()
        assert fs.toolTip().startswith("Filled in from the file size")
    assert checklist_texts(tab, ItemState.TODO) == [
        "Choose a site",
        "Enter fc (MHz) for channel 0, 1, 2, 3",
    ]
    assert checklist_texts(tab, ItemState.ERROR) == []
    assert any(
        t.startswith("fs filled in from the file size for channel 0, 1, 2, 3: 0.001 MHz")
        for t in checklist_texts(tab, ItemState.INFO)
    )
    assert not tab.save_button.isEnabled()


def test_filled_in_fs_follows_sample_type_and_header(qtbot, make_tab, make_recording):
    info = make_recording()  # 4000-byte files
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.INT8))
    assert fs_widget(tab).text() == "0.002"
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.FLOAT32))
    assert fs_widget(tab).text() == "0.0005"
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.INT16))
    tab.header_spin.setValue(3)  # 3997 bytes: not whole int16 samples
    assert fs_widget(tab).text() == ""
    assert any(
        "fs could not be filled in from the file size" in t
        for t in checklist_texts(tab, ItemState.INFO)
    )
    tab.header_spin.setValue(0)
    assert fs_widget(tab).text() == "0.001"


def test_typed_fs_stays(qtbot, make_tab, make_recording):
    info = make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    fs = fs_widget(tab)
    fs.clear()
    qtbot.keyClicks(fs, "0.004")
    assert fs.styleSheet() == ""
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.INT8))
    assert fs.text() == "0.004"
    assert any("differ from the expected size" in t for t in checklist_texts(tab, ItemState.ERROR))


def test_duration_comes_from_the_file_names(qtbot, make_tab, make_recording, site_id):
    info = make_recording(file_duration_s=0.5, n_slots=40)
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    assert tab.duration_spin.value() == 0.5
    assert fs_widget(tab).text() == "0.001"
    assert "File duration set to 0.5 s from the spacing of the file names." in checklist_texts(
        tab, ItemState.INFO
    )
    assert tab.channel_table.item(0, 8).text() == "100.0%"
    assert entry.can_save(tab.checklist.items), checklist_texts(tab)


def test_duration_set_by_the_user_stays(qtbot, make_tab, make_recording):
    info = make_recording(file_duration_s=0.5, n_slots=40)
    tab = make_tab()
    tab.duration_spin.setValue(1.0)
    tab.duration_spin.setValue(2.0)  # the user's choice
    scan_folder(qtbot, tab, info.root)
    assert tab.duration_spin.value() == 2.0
    errors = checklist_texts(tab, ItemState.ERROR)
    assert any(t.startswith("The file names are 0.5 s apart") for t in errors)
    assert any("coverage is" in t for t in errors)


def test_next_folder_gets_its_own_duration(qtbot, make_tab, make_recording):
    half = make_recording(file_duration_s=0.5, n_slots=20)
    whole = make_recording(n_slots=20)
    tab = make_tab()
    scan_folder(qtbot, tab, half.root)
    assert tab.duration_spin.value() == 0.5
    scan_folder(qtbot, tab, whole.root)
    assert tab.duration_spin.value() == 1.0
    assert not any("File duration set" in t for t in checklist_texts(tab))


def test_edit_mode_keeps_stored_fs_and_fills_a_new_channel(
    qtbot, make_tab, make_recording, site_id, db_path
):
    info = make_recording(n_channels=2)
    Path(info.root, "1").rename(Path(info.root, "x1"))
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    fs_widget(tab).clear()
    qtbot.keyClicks(fs_widget(tab), "0.001")  # typed by the user
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert fs_widget(tab).styleSheet() == ""
    Path(info.root, "x1").rename(Path(info.root, "1"))
    tab.start_scan()
    wait_idle(qtbot, tab)
    assert fs_widget(tab, 0).styleSheet() == ""
    assert fs_widget(tab, 1).text() == "0.001"
    assert "italic" in fs_widget(tab, 1).styleSheet()
    assert tab.duration_spin.value() == 1.0
