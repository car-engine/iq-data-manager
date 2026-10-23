"""GUI tests for the Log tab (pytest-qt, offscreen). Data lives in tmp_path.

The tab runs its database and scan work on a thread pool. Each test waits for the
tab's TaskRunner to be idle before it checks results.
"""

import time
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

import iqdm.gui.log_tab as log_tab_module
from conftest import recorder_log_text
from iqdm import entry, recorderlog, templates
from iqdm.config import Config
from iqdm.db import repository
from iqdm.db.connection import DatabaseBusyError, create_database, open_db, write_transaction
from iqdm.entry import ItemState
from iqdm.gui.log_tab import (
    NO_PROJECT,
    REPLACE_TEMPLATE_TITLE,
    LogTab,
    channel_headers,
    replace_template_question,
    scan_summary,
    time_text,
)
from iqdm.gui.widgets.checklist import DARK_COLOURS, LIGHT_COLOURS, MARKS
from iqdm.gui.widgets.template_fields import TemplateFieldsDialog
from iqdm.gui.workers import TaskRunner
from iqdm.location import split_location
from iqdm.models import (
    ArchiveState,
    Endianness,
    IqLayout,
    Operation,
    SampleType,
    TransferEntry,
)
from iqdm.scan.scanner import ScanCancelled, scan_recording
from make_fixtures import ChannelSpec

NAS = r"\\nas\recordings"


@pytest.fixture(autouse=True)
def popups(monkeypatch) -> list[tuple[str, str]]:
    """Record QMessageBox.information calls. A real modal box would block the test."""
    shown: list[tuple[str, str]] = []

    def information(parent, title, text, *args):
        shown.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", information)
    return shown


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


def fill_channels(tab: LogTab, fs_text: str = "1k", fc_mhz: str = "145.8") -> None:
    for c in tab.current_input().channels:
        band, fc, fs = tab.channel_widgets(c.channel_index)
        band.setCurrentText("VHF")
        fc.setText(fc_mhz)
        fs.setText(fs_text)


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
    assert "No database configured" in tab.message_text
    assert not tab.save_button.isEnabled()
    assert tab.mode_label.text() == "New entry"
    assert "Scan the folder" in checklist_texts(tab, ItemState.TODO)


def test_loads_sites_parameter_names_and_bands(make_tab, db_path, site_id, make_recording):
    info = make_recording()
    scan = scan_recording(Path(info.root), 1.0)
    form = entry.EntryInput(
        logged_by="u",
        site_id=site_id,
        channels=[entry.ChannelInput(channel_index=0, band="UHF", fc_mhz="400", fs_text="1k")],
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


def test_logged_by_starts_empty_for_the_user_to_type(make_tab, monkeypatch):
    """D94: the Windows login may name a shared laptop account, so the user types a name."""
    monkeypatch.setattr("iqdm.entry.getpass.getuser", lambda: "lab-laptop")
    tab = make_tab()
    assert tab.logged_by_edit.text() == ""
    assert tab.logged_by_edit.placeholderText() == "Your name"
    assert "Enter the logged-by name" in checklist_texts(tab, ItemState.TODO)


def test_a_typed_name_stays_for_the_next_folder_and_after_a_save(
    qtbot, make_tab, make_recording, site_id
):
    first, second = make_recording(), make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, first, site_id)
    assert tab.logged_by_edit.text() == "userA"
    save_and_wait(qtbot, tab)
    assert tab.logged_by_edit.text() == "userA"
    scan_folder(qtbot, tab, second.root)
    assert tab.logged_by_edit.text() == "userA"
    assert "Enter the logged-by name" not in checklist_texts(tab, ItemState.TODO)


def test_a_typed_name_stays_across_the_mode_switch(make_tab):
    tab = make_tab()
    tab.logged_by_edit.setText("userA")
    tab.several_radio.setChecked(True)
    assert tab.logged_by_edit.text() == "userA"
    tab.one_radio.setChecked(True)  # no folders listed, so no question
    assert tab.logged_by_edit.text() == "userA"


def test_database_that_cannot_be_read_is_reported(make_tab, tmp_path):
    tab = make_tab(Config(db_path=str(tmp_path / "missing.db")))
    assert "Cannot read the database" in tab.message_text


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
    assert tab.state_note.text().startswith("Archive state on save: archived.")


def test_drive_root_cannot_be_logged(make_tab, tmp_path):
    tab = make_tab()
    tab.folder_edit.setText(Path(tmp_path).anchor)
    errors = checklist_texts(tab, ItemState.ERROR)
    assert any(t.startswith("Folder cannot be logged: a drive or share root") for t in errors)
    tab.start_scan()
    assert not tab.runner.busy
    assert tab.message_text.startswith("Folder cannot be logged")


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
    assert tab.channel_table.item(0, 5).text() == "2026-09-30 10:00:00"
    assert tab.channel_table.item(0, 6).text() == "2026-09-30 10:00:10"
    assert tab.channel_table.item(0, 7).text() == "10"
    assert tab.channel_table.item(0, 8).text() == "100.0%"
    assert tab.channel_table.item(1, 7).text() == "9"
    assert tab.channel_table.item(1, 8).text() == "90.0%"
    assert tab.start_edit.text() == "2026-09-30 10:00:00"
    assert tab.end_edit.text() == "2026-09-30 10:00:10"
    summary = tab.scan_summary.text()
    assert summary.startswith("Found channel folders 0 and 1 · 19 files")
    assert "2026-09-30 10:00:00 to 2026-09-30 10:00:10 UTC+8" in summary
    assert "ch 1 has 1 missing second" in summary
    assert "Folder not already in the database" in checklist_texts(tab, ItemState.OK)


def test_the_same_capture_in_another_folder_is_reported(
    qtbot, make_tab, db_path, site_id, make_recording
):
    """D61: two folders with the same files, such as a laptop folder and its hand copy."""
    first = make_recording(n_channels=2, n_slots=5)
    form = entry.EntryInput(
        logged_by="u",
        site_id=site_id,
        channels=[
            entry.ChannelInput(channel_index=i, fc_mhz="400", fs_text="1k") for i in (0, 1)
        ],
    )
    scan = scan_recording(Path(first.root), 1.0)
    rid = entry.save_new(
        db_path, entry.build_recording(form, scan=scan, location=split_location(first.root))
    )
    second = make_recording(n_channels=2, n_slots=5)
    tab = make_tab()
    scan_folder(qtbot, tab, second.root)
    assert (
        f"Recording {rid} has the same start, end and channels. It may be the same capture "
        "in another folder."
    ) in checklist_texts(tab, ItemState.INFO)
    scan_folder(qtbot, tab, first.root)  # the same folder: an error, without the line
    assert not any("same start, end" in t for t in checklist_texts(tab))


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
    assert tab.end_edit.text() == "2026-09-30 10:00:11"
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
    assert tab.message_text == "Saved as recording 1."
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
    assert tab.message_text == "Complete or fix the items in the checklist first."
    assert entry.find_logged(db_path, tab._location) is None


def test_save_failure_is_reported(qtbot, make_tab, make_recording, site_id, monkeypatch):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)

    def busy(db, rec):
        raise DatabaseBusyError("The database is in use by someone else.")

    monkeypatch.setattr("iqdm.entry.save_new", busy)
    save_and_wait(qtbot, tab)
    assert tab.message_text == "Not saved: The database is in use by someone else."
    assert tab.save_button.isEnabled()


def test_add_site(qtbot, make_tab, monkeypatch, db_path):
    tab = make_tab()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("  New site ", True))
    tab.add_site()
    wait_idle(qtbot, tab)
    qtbot.waitUntil(lambda: tab.site_combo.count() == 1)
    wait_idle(qtbot, tab)
    assert tab.site_combo.currentText() == "New site"
    assert tab.message_text == "Added site New site."


def test_add_duplicate_site_is_reported(qtbot, make_tab, monkeypatch, site_id):
    tab = make_tab()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("sitea", True))
    tab.add_site()
    wait_idle(qtbot, tab)
    assert tab.message_text.startswith("Site not added:")


# ---------------------------------------------------------------------------
# Projects (DECISIONS.md D73)
# ---------------------------------------------------------------------------


def project_names(tab: LogTab) -> list[str]:
    return [tab.project_combo.itemText(i) for i in range(tab.project_combo.count())]


def test_the_project_starts_empty_and_lists_the_projects(qtbot, make_tab, db_path):
    entry.add_project(db_path, "Survey")
    entry.add_project(db_path, "antenna trial")
    tab = make_tab()
    assert project_names(tab) == [NO_PROJECT, "antenna trial", "Survey"]
    assert tab.project_combo.currentData() is None
    assert tab.current_input().project_id is None


def test_add_project_selects_it(qtbot, make_tab, monkeypatch):
    tab = make_tab()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("  Radar Trial ", True))
    tab.add_project()
    wait_idle(qtbot, tab)
    qtbot.waitUntil(lambda: tab.project_combo.count() == 2)
    wait_idle(qtbot, tab)
    assert tab.project_combo.currentText() == "Radar Trial"
    assert tab.message_text == "Added project Radar Trial."


def test_add_duplicate_project_is_reported(qtbot, make_tab, monkeypatch, db_path):
    entry.add_project(db_path, "Radar Trial")
    tab = make_tab()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("radar trial", True))
    tab.add_project()
    wait_idle(qtbot, tab)
    assert tab.message_text.startswith("Project not added:")


def test_save_with_and_without_a_project(qtbot, make_tab, make_recording, site_id, db_path):
    project = entry.add_project(db_path, "Radar Trial").id
    tab = make_tab()
    logged_ready(qtbot, tab, make_recording(), site_id)
    save_and_wait(qtbot, tab)  # no project: optional
    assert tab.message_text == "Saved as recording 1.", checklist_texts(tab)
    assert entry.load_recording(db_path, 1).project_id is None
    tab.clear_form()
    logged_ready(qtbot, tab, make_recording(), site_id)
    tab.project_combo.setCurrentIndex(tab.project_combo.findData(project))
    save_and_wait(qtbot, tab)
    assert entry.load_recording(db_path, 2).project_id == project


def test_edit_changes_the_project_without_a_rescan(
    qtbot, make_tab, make_recording, site_id, db_path
):
    project = entry.add_project(db_path, "Radar Trial").id
    info = make_recording(n_channels=2)
    tab = saved_tab(qtbot, make_tab, info, site_id)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert tab.project_combo.currentData() is None
    tab.project_combo.setCurrentIndex(tab.project_combo.findData(project))
    save_and_wait(qtbot, tab)
    assert tab.message_text == "Saved changes to recording 1."
    assert entry.load_recording(db_path, 1).project_id == project
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert tab.project_combo.currentData() == project
    tab.project_combo.setCurrentIndex(0)  # back to no project
    save_and_wait(qtbot, tab)
    assert entry.load_recording(db_path, 1).project_id is None


def test_clear_form_resets_every_field(qtbot, make_tab, make_recording, site_id, monkeypatch):
    monkeypatch.setattr("iqdm.entry.getpass.getuser", lambda: "lab-laptop")
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
    assert tab.logged_by_edit.text() == ""  # D94: empty, not the Windows login
    assert (tab.plan_edit.text(), tab.remarks_edit.toPlainText()) == ("", "")
    assert tab.duration_spin.value() == 1.0
    assert tab.header_spin.value() == 0
    assert tab.site_combo.currentIndex() == -1
    assert tab.project_combo.currentData() is None
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
    assert tab.message_text == "Saved as recording 1.", checklist_texts(tab)
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
    assert tab.message_text == "Saved changes to recording 1."
    rec = entry.load_recording(db_path, 1)
    assert rec.remarks == "edited"
    assert rec.channels[1].fc_hz == 433_920_000.0
    assert tab.editing is not None
    assert tab.editing.remarks == "edited"


def test_an_edit_of_an_entry_archived_meanwhile_is_refused(
    qtbot, make_tab, make_recording, site_id, db_path
):
    """The entry was archived after the edit opened; the save writes nothing (D76)."""
    info = make_recording(n_channels=2)
    tab = saved_tab(qtbot, make_tab, info, site_id)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    write_transaction(
        db_path,
        lambda conn: repository.update_archive_location(
            conn, 1, storage_root=NAS, rel_path="2026\\rec", archived_at="2026-10-11T08:00:00Z"
        ),
    )
    saves: list[int] = []
    tab.saved.connect(saves.append)
    tab.remarks_edit.setPlainText("typo fixed")
    save_and_wait(qtbot, tab)
    assert tab.message_text == (
        "Not saved: Recording 1 changed after you opened it, for example by an archive or "
        "a check. Open it again with Edit entry and make the change there."
    )
    assert saves == []
    assert tab.remarks_edit.toPlainText() == "typo fixed"  # the form stays
    rec = entry.load_recording(db_path, 1)
    assert (rec.storage_root, rec.archive_state) == (NAS, ArchiveState.ARCHIVED)
    assert rec.remarks is None


def test_an_edit_without_changes_writes_nothing(qtbot, make_tab, make_recording, site_id, db_path):
    info = make_recording(n_channels=2)
    tab = saved_tab(qtbot, make_tab, info, site_id)
    before = entry.load_recording(db_path, 1).updated_at
    saves: list[int] = []
    tab.saved.connect(saves.append)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    tab.save_button.click()
    wait_idle(qtbot, tab)
    assert tab.message_text == "No changes to save."
    assert saves == []
    assert not tab.is_saving
    assert entry.load_recording(db_path, 1).updated_at == before
    assert tab.editing is not None  # still in edit mode


def test_edit_of_fs_needs_a_rescan(qtbot, make_tab, make_recording, site_id):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    tab.channel_widgets(0)[2].setText("2k")
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
    assert tab.message_text == (
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
        assert tab.message_text == (
            "Nothing saved. The channels and their RF chain rows stay in the database. "
            "Open the entry again to see the stored rows."
        )
        assert [c.channel_index for c in rec.channels] == [0, 1]
        assert len(rec.params) == 1
    else:
        assert tab.message_text == "Saved changes to recording 1."
        assert [c.channel_index for c in rec.channels] == [0]
        assert rec.params == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_time_text_uses_the_display_offset():
    assert time_text(1790733600.0, 8.0) == "2026-09-30 10:00:00"
    assert time_text(1790733600.0, 0.0) == "2026-09-30 02:00:00"
    assert time_text(None, 8.0) == ""


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
    assert tab.message_text == ""


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
        assert fs.text() == "1 kHz"
        assert "italic" in fs.styleSheet()
        assert fs.toolTip().startswith("Filled in from the file size")
    assert checklist_texts(tab, ItemState.TODO) == [
        "Enter the logged-by name",
        "Choose a site",
        "Enter fc (MHz) for channel 0, 1, 2, 3",
    ]
    assert checklist_texts(tab, ItemState.ERROR) == []
    assert any(
        t.startswith("fs filled in from the file size for channel 0, 1, 2, 3: 1 kHz")
        for t in checklist_texts(tab, ItemState.INFO)
    )
    assert not tab.save_button.isEnabled()


def test_filled_in_fs_follows_sample_type_and_header(qtbot, make_tab, make_recording):
    info = make_recording()  # 4000-byte files
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.INT8))
    assert fs_widget(tab).text() == "2 kHz"
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.FLOAT32))
    assert fs_widget(tab).text() == "500 Hz"
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.INT16))
    tab.header_spin.setValue(3)  # 3997 bytes: not whole int16 samples
    assert fs_widget(tab).text() == ""
    assert any(
        "fs could not be filled in from the file size" in t
        for t in checklist_texts(tab, ItemState.INFO)
    )
    tab.header_spin.setValue(0)
    assert fs_widget(tab).text() == "1 kHz"


def test_typed_fs_stays(qtbot, make_tab, make_recording):
    info = make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    fs = fs_widget(tab)
    fs.clear()
    qtbot.keyClicks(fs, "4k")
    assert fs.styleSheet() == ""
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.INT8))
    assert fs.text() == "4k"
    assert any("differ from the expected size" in t for t in checklist_texts(tab, ItemState.ERROR))


def test_duration_comes_from_the_file_names(qtbot, make_tab, make_recording, site_id):
    info = make_recording(file_duration_s=0.5, n_slots=40)
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    assert tab.duration_spin.value() == 0.5
    assert fs_widget(tab).text() == "1k"  # typed by logged_ready()
    assert "File duration set to 0.5 s from the spacing of the file names." in checklist_texts(
        tab, ItemState.INFO
    )
    assert tab.channel_table.item(0, 8).text() == "100.0%"
    assert entry.can_save(tab.checklist.items), checklist_texts(tab)


def test_duration_set_by_the_user_stays(qtbot, make_tab, make_recording):
    info = make_recording(file_duration_s=0.5, n_slots=40)
    tab = make_tab()
    tab.folder_edit.setText(info.root)
    tab.duration_spin.setValue(2.0)  # the user's choice, after choosing the folder
    tab.start_scan()
    wait_idle(qtbot, tab)
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
    qtbot.keyClicks(fs_widget(tab), "1k")  # typed by the user
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert fs_widget(tab).styleSheet() == ""
    Path(info.root, "x1").rename(Path(info.root, "1"))
    tab.start_scan()
    wait_idle(qtbot, tab)
    assert fs_widget(tab, 0).styleSheet() == ""
    assert fs_widget(tab, 1).text() == "1 kHz"
    assert "italic" in fs_widget(tab, 1).styleSheet()
    assert tab.duration_spin.value() == 1.0


# ---------------------------------------------------------------------------
# Feedback after the first manual test (2026-10-02)
# ---------------------------------------------------------------------------


def test_save_shows_a_popup(qtbot, make_tab, make_recording, site_id, popups):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    save_and_wait(qtbot, tab)
    ((title, text),) = popups
    assert title == "Recording saved"
    assert text.startswith("Saved as recording 1.")
    assert "Archive state: local" in text
    assert Path(text.split("Folder: ")[1].splitlines()[0]) == Path(info.root)


def test_saving_an_edit_shows_a_popup(qtbot, make_tab, make_recording, site_id, popups):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    tab.remarks_edit.setPlainText("edited")
    save_and_wait(qtbot, tab)
    assert popups[-1] == ("Recording saved", "Saved changes to recording 1.")


def test_messages_clear_for_a_new_folder(qtbot, make_tab, make_recording, site_id):
    first, second = make_recording(), make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, first, site_id)
    save_and_wait(qtbot, tab)
    assert tab.message_text == "Saved as recording 1."
    tab.folder_edit.setText(second.root)
    assert tab.message_text == ""
    tab.show_message("old")
    tab.start_scan()
    assert tab.message_text == ""
    wait_idle(qtbot, tab)
    assert tab.state_note.text().startswith("Archive state on save: local.")


def test_times_use_the_configured_offset(qtbot, make_tab, make_recording, db_path):
    info = make_recording(n_slots=10)
    tab = make_tab(Config(db_path=str(db_path), display_utc_offset_hours=0.0))
    scan_folder(qtbot, tab, info.root)
    header = tab.channel_table.horizontalHeaderItem
    assert (header(5).text(), header(6).text()) == ("Start (UTC)", "End (UTC)")
    assert tab.start_edit.text() == "2026-09-30 02:00:00"
    assert "2026-09-30 02:00:00 to 2026-09-30 02:00:10 UTC" in tab.scan_summary.text()


def test_default_offset_labels_say_utc_plus_8(make_tab):
    tab = make_tab()
    header = tab.channel_table.horizontalHeaderItem
    assert (header(5).text(), header(6).text()) == ("Start (UTC+8)", "End (UTC+8)")
    assert header(4).text() == "fs"


def test_read_only_fields_look_read_only(make_tab):
    tab = make_tab()
    editable = tab.logged_by_edit.palette().color(QPalette.ColorRole.Base)
    for field in (tab.start_edit, tab.end_edit, tab.storage_root_edit, tab.rel_path_edit):
        assert field.isReadOnly()
        assert field.palette().color(QPalette.ColorRole.Base) != editable
        assert field.toolTip() == "Filled in by the app. You cannot edit this field."
    assert not tab.folder_edit.isReadOnly()
    assert tab.folder_edit.palette().color(QPalette.ColorRole.Base) == editable


def test_folder_looks_read_only_in_edit_mode(qtbot, make_tab, make_recording, site_id):
    info = make_recording()
    tab = make_tab()
    editable = tab.logged_by_edit.palette().color(QPalette.ColorRole.Base)
    logged_ready(qtbot, tab, info, site_id)
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert tab.folder_edit.palette().color(QPalette.ColorRole.Base) != editable
    tab.clear_form()
    assert tab.folder_edit.palette().color(QPalette.ColorRole.Base) == editable


@pytest.mark.parametrize(("typed", "hz"), [("10M", 10e6), ("12.5 kHz", 12_500.0), ("500", 500.0)])
def test_fs_accepts_units(qtbot, make_tab, make_recording, typed, hz):
    info = make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    fs = fs_widget(tab)
    fs.clear()
    qtbot.keyClicks(fs, typed)
    assert entry.parse_frequency(tab.current_input().channels[0].fs_text) == hz


def test_fs_with_an_unknown_unit_is_an_error(qtbot, make_tab, make_recording):
    info = make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    fs = fs_widget(tab)
    fs.clear()
    qtbot.keyClicks(fs, "1 mhz")
    assert any(
        t.startswith("Channel 0: fs is not understood: '1 mhz'")
        for t in checklist_texts(tab, ItemState.ERROR)
    )


def test_new_folder_keeps_format_channels_and_rf_chain(qtbot, make_tab, make_recording, site_id):
    """DECISIONS.md D79, which replaces D26: only the values from the scan reset."""
    first = make_recording(n_channels=2, dtype="int8", header_bytes=64)
    second = make_recording(n_channels=2, dtype="int8", header_bytes=64)
    tab = make_tab()
    scan_folder(qtbot, tab, first.root)
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.INT8))
    tab.layout_combo.setCurrentIndex(tab.layout_combo.findData(IqLayout.PLANAR_IQ))
    tab.endian_combo.setCurrentIndex(tab.endian_combo.findData(Endianness.BIG))
    tab.header_spin.setValue(64)
    tab.duration_spin.setValue(2.0)
    fill_channels(tab, fs_text="2k")
    tab.channel_widgets(1)[1].setText("435")
    tab.param_table.add_row(entry.ParamInput(param="SDR", value="X310"))
    tab.param_table.add_row(entry.ParamInput(param="Antenna", value="Yagi", channel_index=1))
    choose_site(tab, site_id)
    tab.logged_by_edit.setText("userB")
    tab.plan_edit.setText("plan-9")
    assert tab.kept_note.isHidden()

    scan_folder(qtbot, tab, second.root)
    assert tab.dtype_combo.currentData() == SampleType.INT8
    assert tab.layout_combo.currentData() == IqLayout.PLANAR_IQ
    assert tab.endian_combo.currentData() == Endianness.BIG
    assert tab.header_spin.value() == 64
    assert tab.duration_spin.value() == 1.0  # from the new file names
    assert [(p.param, p.channel_index) for p in tab.param_table.rows()] == [
        ("SDR", None),
        ("Antenna", 1),
    ]
    # Channel 1's band VHF followed its fc to UHF when 435 was typed (D88).
    for index, band_name, fc_mhz in ((0, "VHF", "145.8"), (1, "UHF", "435")):
        band, fc, fs = tab.channel_widgets(index)
        assert (band.currentText(), fc.text()) == (band_name, fc_mhz)
        assert fs.text() == "1 kHz"  # filled in again from the scan, for the kept int8
        assert "italic" in fs.styleSheet()
    assert tab.site_combo.currentData() == site_id
    assert tab.logged_by_edit.text() == "userB"
    assert tab.plan_edit.text() == "plan-9"
    assert not tab.kept_note.isHidden()
    assert tab.kept_note.text().startswith(
        f"{MARKS[ItemState.INFO]}  "
        "Kept from the previous entry: int8, planar_iq, big-endian, header 64 bytes; "
        "band and fc of 2 channels; 2 RF chain rows."
    )
    assert tab.message_text == ""


def test_typing_a_folder_keeps_the_rf_chain(qtbot, make_tab, make_recording):
    """D79: the folder field changes on each key; nothing typed elsewhere is lost."""
    info = make_recording(n_channels=2)
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    fill_channels(tab)
    tab.param_table.add_row(entry.ParamInput(param="LNA", value="20", channel_index=1))
    tab.folder_edit.clear()
    qtbot.keyClicks(tab.folder_edit, "C:")
    assert [p.param for p in tab.param_table.rows()] == ["LNA"]
    assert tab.channel_table.rowCount() == 0
    # Before a scan the channels are unknown, so a channel row is not an error yet.
    assert not any("is not in this recording" in t for t in checklist_texts(tab))
    scan_folder(qtbot, tab, info.root)
    assert tab.channel_widgets(1)[0].currentText() == "VHF"


def test_values_of_channels_the_new_folder_lacks_are_removed(qtbot, make_tab, make_recording):
    """D79: settings for channel 1 go when the next folder has channel 0 only."""
    two = make_recording(n_channels=2)
    one = make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, two.root)
    fill_channels(tab)
    tab.param_table.add_row(entry.ParamInput(param="SDR", value="X310"))
    tab.param_table.add_row(entry.ParamInput(param="Antenna", value="Yagi", channel_index=1))
    tab.param_table.add_row(entry.ParamInput(param="LNA", value="20", channel_index=1))
    scan_folder(qtbot, tab, one.root)
    assert [p.param for p in tab.param_table.rows()] == ["SDR"]
    assert tab.message_text == (
        "This folder has no channel 1. "
        "Removed from the form: band and fc, 2 RF chain rows of that channel."
    )
    assert tab.channel_widgets(0)[0].currentText() == "VHF"
    assert not any("is not in this recording" in t for t in checklist_texts(tab))
    assert "band and fc of 1 channel; 1 RF chain row." in tab.kept_note.text()
    # Channel 1 does not come back for a later folder that has it.
    scan_folder(qtbot, tab, two.root)
    assert tab.channel_widgets(1)[1].text() == ""


def test_clear_form_drops_the_kept_values(qtbot, make_tab, make_recording):
    first, second = make_recording(), make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, first.root)
    fill_channels(tab)
    tab.header_spin.setValue(8)
    scan_folder(qtbot, tab, second.root)
    assert not tab.kept_note.isHidden()
    tab.clear_form()
    assert tab.kept_note.isHidden()
    assert tab.header_spin.value() == 0
    scan_folder(qtbot, tab, first.root)
    assert tab.channel_widgets(0)[1].text() == ""
    assert tab.kept_note.isHidden()


def test_no_note_when_nothing_but_defaults_is_kept(qtbot, make_tab, make_recording):
    first, second = make_recording(), make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, first.root)
    scan_folder(qtbot, tab, second.root)
    assert tab.kept_note.isHidden()


def test_edit_mode_shows_no_kept_note(qtbot, make_tab, make_recording, site_id):
    first, second = make_recording(), make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, first, site_id)
    save_and_wait(qtbot, tab)
    scan_folder(qtbot, tab, second.root)
    assert not tab.kept_note.isHidden()
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert tab.kept_note.isHidden()
    assert tab.channel_widgets(0)[1].text() == "145.8"  # the stored value


# ---------------------------------------------------------------------------
# Values from the recorder's log (D82)
# ---------------------------------------------------------------------------


def with_recorder_log(info, channels, **kw) -> str:
    """Write a recorder log next to a generated recording. Returns the folder."""
    root = Path(info.root)
    (root / f"recorder_{root.name}.log").write_text(
        recorder_log_text(channels, **kw), encoding="utf-8"
    )
    return info.root


def rows_of(tab: LogTab) -> list[tuple[int | None, str, str, str]]:
    return [(p.channel_index, p.param, p.value, p.unit) for p in tab.param_table.rows()]


def test_a_scan_fills_values_from_the_recorder_log(qtbot, make_tab, make_recording, site_id):
    info = make_recording(n_channels=2, n_slots=6)
    folder = with_recorder_log(info, {0: (300.0, 30.0), 1: (433.0, 30.0)}, files_written=12)
    tab = make_tab()
    scan_folder(qtbot, tab, folder)
    for index, fc_mhz in ((0, "300"), (1, "433")):
        _band, fc, fs = tab.channel_widgets(index)
        assert fc.text() == fc_mhz
        assert fs.text() == "1 kHz"
        assert "italic" in fc.styleSheet() and "italic" in fs.styleSheet()
        assert fc.toolTip() == recorderlog.FROM_LOG_TOOLTIP
    assert tab.dtype_combo.currentData() == SampleType.INT16
    assert rows_of(tab) == [
        (None, "USRP gain", "30", "dB"),
        (None, "Clock reference", "GPSDO", ""),
        (None, "USRP", "X310 + UBX", ""),
    ]
    info_lines = checklist_texts(tab, ItemState.INFO)
    filled = "Filled in from the recorder's log: sample type int16"
    assert any(t.startswith(filled) for t in info_lines)
    assert not any("not recognised" in t for t in checklist_texts(tab))
    assert not checklist_texts(tab, ItemState.ERROR)  # the size check agrees with the log's fs
    choose_site(tab, site_id)
    tab.logged_by_edit.setText("userA")
    save_and_wait(qtbot, tab)
    assert tab.message_text == "Saved as recording 1."


def test_the_log_replaces_kept_values_but_not_a_usrp_row(qtbot, make_tab, make_recording):
    """D82 over D79: the log describes this folder; a template's USRP-2954 stays."""
    first, second = make_recording(), make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, first.root)
    tab.dtype_combo.setCurrentIndex(tab.dtype_combo.findData(SampleType.INT8))
    fill_channels(tab, fc_mhz="145.8")
    tab.param_table.add_row(entry.ParamInput(param="USRP", value="USRP-2954"))
    tab.param_table.add_row(entry.ParamInput(param="USRP Gain", value="10", unit="dB"))
    tab.param_table.add_row(entry.ParamInput(param="Antenna", value="Yagi"))
    folder = with_recorder_log(second, {0: (300.0, 30.0)}, ref="internal")
    scan_folder(qtbot, tab, folder)
    assert tab.dtype_combo.currentData() == SampleType.INT16  # was int8, kept
    assert tab.channel_widgets(0)[1].text() == "300"  # was 145.8, kept
    assert rows_of(tab) == [
        (None, "USRP", "USRP-2954", ""),
        (None, "Antenna", "Yagi", ""),
        (None, "USRP gain", "30", "dB"),  # replaces the kept "USRP Gain" row
        (None, "Clock reference", "Internal", ""),
    ]
    assert any("from the PC clock" in t for t in checklist_texts(tab, ItemState.INFO))


def test_typing_ends_the_mark_and_a_rescan_does_not_fill_again(qtbot, make_tab, make_recording):
    info = make_recording()
    folder = with_recorder_log(info, {0: (300.0, 30.0)})
    tab = make_tab()
    scan_folder(qtbot, tab, folder)
    fc = tab.channel_widgets(0)[1]
    fc.clear()
    qtbot.keyClicks(fc, "301")
    assert fc.styleSheet() == ""
    tab.param_table.set_rows([entry.ParamInput(param="USRP Gain", value="12", unit="dB")])
    tab.start_scan()  # the same folder again
    wait_idle(qtbot, tab)
    assert tab.channel_widgets(0)[1].text() == "301"
    assert rows_of(tab) == [(None, "USRP Gain", "12", "dB")]
    assert "italic" in tab.channel_widgets(0)[2].styleSheet()  # fs is still from the log


def test_a_file_count_that_differs_does_not_block_saving(
    qtbot, make_tab, make_recording, site_id
):
    info = make_recording(n_slots=5)
    folder = with_recorder_log(info, {0: (300.0, 30.0)}, files_written=7)
    tab = make_tab()
    scan_folder(qtbot, tab, folder)
    assert (
        "The recorder wrote 7 files; the folder holds 5. 2 files went missing after recording."
        in checklist_texts(tab, ItemState.INFO)
    )
    choose_site(tab, site_id)
    tab.logged_by_edit.setText("userA")
    tab.refresh_checklist()
    assert tab.save_button.isEnabled()


def test_edit_mode_reads_the_log_but_fills_nothing(qtbot, make_tab, make_recording, site_id):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)  # fc 145.8, typed before the log exists
    save_and_wait(qtbot, tab)
    with_recorder_log(info, {0: (300.0, 30.0)}, gps_locked=False)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    tab.start_scan()
    wait_idle(qtbot, tab)
    assert tab.channel_widgets(0)[1].text() == "145.8"
    assert rows_of(tab) == []
    assert "The recorder's log says GPS was not locked." in checklist_texts(tab, ItemState.INFO)


def test_the_command_line_file_alone_fills_fc_and_fs(qtbot, make_tab, make_recording):
    info = make_recording(n_channels=2)
    (Path(info.root) / "log.txt").write_text(
        "--ref external --channels 0,1 --freq 145.8e6,435e6 --rate 1e3 --gain 25\n",
        encoding="utf-8",
    )
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    assert [tab.channel_widgets(i)[1].text() for i in (0, 1)] == ["145.8", "435"]
    assert tab.channel_widgets(0)[2].text() == "1 kHz"
    assert rows_of(tab) == [
        (None, "USRP gain", "25", "dB"),
        (None, "Clock reference", "External", ""),
    ]


def test_log_rows_take_the_catalogue_spelling(qtbot, make_tab, make_recording, site_id):
    """Review of 1.1.0, finding 3: no line about a spelling the save would change."""
    first, second = make_recording(), make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, first, site_id)
    tab.param_table.add_row(entry.ParamInput(param="usrp GAIN", value="20", unit="dB"))
    save_and_wait(qtbot, tab)
    assert "usrp GAIN" in tab._choices.param_names
    tab.param_table.set_rows([])
    scan_folder(qtbot, tab, with_recorder_log(second, {0: (300.0, 30.0)}))
    assert (None, "usrp GAIN", "30", "dB") in rows_of(tab)
    assert not any("will be saved as" in t for t in checklist_texts(tab))


def test_a_kept_row_of_a_missing_channel_does_not_stop_the_log(qtbot, make_tab, make_recording):
    """Review of 1.1.0, finding 8: kept rows of missing channels go before the log fills."""
    first, second = make_recording(n_channels=3), make_recording(n_channels=2)
    tab = make_tab()
    scan_folder(qtbot, tab, first.root)
    tab.param_table.add_row(entry.ParamInput(param="USRP", value="B210", channel_index=2))
    scan_folder(qtbot, tab, with_recorder_log(second, {0: (300.0, 30.0), 1: (433.0, 30.0)}))
    assert (None, "USRP", "X310 + UBX", "") in rows_of(tab)
    assert all(row[0] != 2 for row in rows_of(tab))


# ---------------------------------------------------------------------------
# A template imported after the log filled the form (D87)
# ---------------------------------------------------------------------------


@pytest.fixture
def conflict_answer(monkeypatch):
    """Replace the pop-up: record the conflicts it shows and give a set answer."""
    asked: list[list[recorderlog.Conflict]] = []
    answer = {"choice": log_tab_module.ConflictChoice.KEEP_LOG}

    def ask(parent, conflicts):
        asked.append(list(conflicts))
        return answer["choice"]

    monkeypatch.setattr(log_tab_module, "ask_template_conflicts", ask)
    return asked, answer


def log_scanned_tab(qtbot, make_tab, make_recording) -> LogTab:
    """A one-channel folder at 300 MHz, 30 dB, GPSDO, X310 + UBX, filled from its log."""
    tab = make_tab()
    scan_folder(qtbot, tab, with_recorder_log(make_recording(), {0: (300.0, 30.0)}))
    return tab


def set_up_template(tmp_path: Path) -> Path:
    path = tmp_path / "set-up.toml"
    templates.write_template(
        path,
        templates.LogTemplate(
            remarks="Hilltop mast",
            sample_type=SampleType.INT8,
            channels=(templates.TemplateChannel(index=0, band="VHF", fc_mhz="145.8"),),
            rf_chain=(
                entry.ParamInput(param="Antenna", value="Yagi"),
                entry.ParamInput(param="USRP gain", value="10", unit="dB"),
            ),
        ),
    )
    return path


def test_the_popup_names_each_log_value_the_template_replaces(
    qtbot, make_tab, make_recording, tmp_path, conflict_answer
):
    asked, _ = conflict_answer
    tab = log_scanned_tab(qtbot, make_tab, make_recording)
    tab.import_template(set_up_template(tmp_path))
    (conflicts,) = asked
    assert [(c.what, c.log_text, c.template_text) for c in conflicts] == [
        ("sample type", "int16", "int8"),
        ("fc of channel 0", "300 MHz", "145.8 MHz"),
        ("USRP gain", "30 dB", "10 dB"),
        ("Clock reference", "GPSDO", "no row"),
        ("USRP", "X310 + UBX", "no row"),
    ]


def test_keep_the_log_values(qtbot, make_tab, make_recording, tmp_path, conflict_answer):
    tab = log_scanned_tab(qtbot, make_tab, make_recording)
    tab.import_template(set_up_template(tmp_path))
    band, fc, _fs = tab.channel_widgets(0)
    assert (band.currentText(), fc.text()) == ("VHF", "300")  # the template's band
    assert fc.toolTip() == recorderlog.FROM_LOG_TOOLTIP
    assert tab.dtype_combo.currentData() == SampleType.INT16
    assert tab.remarks_edit.toPlainText() == "Hilltop mast"
    assert rows_of(tab) == [
        (None, "Antenna", "Yagi", ""),
        (None, "USRP gain", "30", "dB"),
        (None, "Clock reference", "GPSDO", ""),
        (None, "USRP", "X310 + UBX", ""),
    ]
    assert tab.message_state is ItemState.INFO
    assert tab.message_text.endswith(
        "Kept from the recorder's log: sample type, fc of channel 0, USRP gain, "
        "Clock reference, USRP."
    )
    filled = [t for t in checklist_texts(tab, ItemState.INFO) if t.startswith("Filled in")]
    assert filled[0].startswith(
        "Filled in from the recorder's log: sample type int16, fc of channel 0, fs of "
        "channel 0, USRP gain, Clock reference, USRP."
    )


def test_use_the_template_values(qtbot, make_tab, make_recording, tmp_path, conflict_answer):
    _, answer = conflict_answer
    answer["choice"] = log_tab_module.ConflictChoice.USE_TEMPLATE
    tab = log_scanned_tab(qtbot, make_tab, make_recording)
    tab.import_template(set_up_template(tmp_path))
    _band, fc, fs = tab.channel_widgets(0)
    assert fc.text() == "145.8"
    assert fc.styleSheet() == "" and fc.toolTip() == ""  # no longer marked as from the log
    assert "italic" in fs.styleSheet()  # fs is still the log's
    assert tab.dtype_combo.currentData() == SampleType.INT8
    assert rows_of(tab) == [(None, "Antenna", "Yagi", ""), (None, "USRP gain", "10", "dB")]
    assert "The template replaced the values from the recorder's log" in tab.message_text
    filled = [t for t in checklist_texts(tab, ItemState.INFO) if t.startswith("Filled in")]
    assert filled[0].startswith("Filled in from the recorder's log: fs of channel 0.")


def test_cancel_leaves_the_form(qtbot, make_tab, make_recording, tmp_path, conflict_answer):
    _, answer = conflict_answer
    answer["choice"] = log_tab_module.ConflictChoice.CANCEL
    tab = log_scanned_tab(qtbot, make_tab, make_recording)
    before = (typed_fields(tab), tab.channel_widgets(0)[1].styleSheet())
    tab.import_template(set_up_template(tmp_path))
    assert (typed_fields(tab), tab.channel_widgets(0)[1].styleSheet()) == before
    assert (tab.message_state, tab.message_text) == (ItemState.INFO, "Template not loaded.")


def test_no_popup_without_a_conflict_or_before_the_scan(
    qtbot, make_tab, make_recording, tmp_path, conflict_answer
):
    asked, _ = conflict_answer
    same = tmp_path / "same.toml"
    templates.write_template(
        same,
        templates.LogTemplate(
            sample_type=SampleType.INT16,
            channels=(templates.TemplateChannel(index=0, band="VHF", fc_mhz="300.0"),),
        ),
    )
    tab = log_scanned_tab(qtbot, make_tab, make_recording)
    tab.import_template(same)  # the same values as the log
    assert tab.channel_widgets(0)[0].currentText() == "VHF"
    assert tab.message_state is ItemState.OK
    tab.clear_form()
    tab.import_template(set_up_template(tmp_path))  # before the scan: the log wins later
    scan_folder(qtbot, tab, with_recorder_log(make_recording(), {0: (300.0, 30.0)}))
    assert tab.channel_widgets(0)[1].text() == "300"
    assert asked == []


# ---------------------------------------------------------------------------
# The band from fc (D88)
# ---------------------------------------------------------------------------


def band_text(tab: LogTab, index: int = 0) -> str:
    return tab.channel_widgets(index)[0].currentText()


def is_italic(widget) -> bool:
    return "italic" in widget.styleSheet()


def type_band(qtbot, tab: LogTab, text: str, index: int = 0) -> None:
    band = tab.channel_widgets(index)[0]
    band.lineEdit().clear()
    qtbot.keyClicks(band.lineEdit(), text)


def outside_lines(tab: LogTab) -> list[str]:
    return [t for t in checklist_texts(tab, ItemState.INFO) if "is outside" in t]


def test_the_box_lists_the_bands_with_an_empty_catalogue(qtbot, make_tab, make_recording):
    tab = make_tab()
    scan_folder(qtbot, tab, make_recording().root)
    band = tab.channel_widgets(0)[0]
    assert [band.itemText(i) for i in range(band.count())] == [
        "HF", "VHF", "UHF", "L", "S", "C", "X", "Ku", "K", "Ka"
    ]  # fmt: skip
    assert band.currentText() == ""
    assert band.toolTip() == log_tab_module.BAND_TOOLTIP


def test_typing_fc_fills_the_band_in_italics(qtbot, make_tab, make_recording):
    tab = make_tab()
    scan_folder(qtbot, tab, make_recording().root)
    band, fc, _fs = tab.channel_widgets(0)
    qtbot.keyClicks(fc, "145.8")
    assert band.currentText() == "VHF"
    assert is_italic(band)
    assert band.toolTip() == (
        "Filled in from fc: VHF is 30 to 300 MHz. Pick or type another band to replace it."
    )
    fc.clear()
    qtbot.keyClicks(fc, "2")  # 2 MHz is in no band
    assert band.currentText() == ""
    assert not is_italic(band)


def test_a_band_the_user_chose_stays(qtbot, make_tab, make_recording):
    tab = make_tab()
    scan_folder(qtbot, tab, make_recording().root)
    band, fc, _fs = tab.channel_widgets(0)
    qtbot.keyClicks(fc, "145.8")
    type_band(qtbot, tab, "L")
    assert not is_italic(band)
    fc.setText("433")
    assert band.currentText() == "L"
    assert outside_lines(tab) == [
        "Channel 0: fc 433 MHz is outside L (1 to 2 GHz). Check the band."
    ]
    band.setCurrentIndex(band.findText("UHF"))  # picked from the list
    band.activated.emit(band.currentIndex())
    assert not is_italic(band)
    assert outside_lines(tab) == []


def test_the_logs_fc_moves_a_kept_band(qtbot, make_tab, make_recording):
    """The 1.1.1 manual test: folder B kept UHF from folder A, and its log gave 145.8 MHz."""
    tab = make_tab()
    scan_folder(qtbot, tab, make_recording().root)
    type_band(qtbot, tab, "UHF")
    tab.channel_widgets(0)[1].setText("433")
    folder = with_recorder_log(make_recording(), {0: (145.8, 30.0)})
    scan_folder(qtbot, tab, folder)
    band, fc, _fs = tab.channel_widgets(0)
    assert (band.currentText(), fc.text()) == ("VHF", "145.8")
    assert is_italic(band)
    assert outside_lines(tab) == []


def test_a_kept_band_that_differs_from_its_fc_stays(qtbot, make_tab, make_recording):
    tab = make_tab()
    scan_folder(qtbot, tab, make_recording().root)
    type_band(qtbot, tab, "L")
    tab.channel_widgets(0)[1].setText("145.8")  # L was chosen against this fc
    scan_folder(qtbot, tab, with_recorder_log(make_recording(), {0: (433.0, 30.0)}))
    assert band_text(tab) == "L"
    assert outside_lines(tab) == [
        "Channel 0: fc 433 MHz is outside L (1 to 2 GHz). Check the band."
    ]


def test_a_kept_fc_without_a_band_fills_the_band(qtbot, make_tab, make_recording):
    tab = make_tab()
    scan_folder(qtbot, tab, make_recording().root)
    tab.channel_widgets(0)[1].setText("433")
    type_band(qtbot, tab, "")
    scan_folder(qtbot, tab, make_recording().root)
    assert band_text(tab) == "UHF"
    assert is_italic(tab.channel_widgets(0)[0])


def test_a_down_converted_fc_typed_over_the_logs(qtbot, make_tab, make_recording):
    """fc is the frequency on air: typed over the tuned frequency, the band follows."""
    tab = make_tab()
    scan_folder(qtbot, tab, with_recorder_log(make_recording(), {0: (1200.0, 30.0)}))
    band, fc, _fs = tab.channel_widgets(0)
    assert band.currentText() == "L"
    fc.clear()
    qtbot.keyClicks(fc, "14250")
    assert band.currentText() == "Ku"
    assert not is_italic(fc)  # no longer the log's value


def test_a_templates_band_wins(qtbot, make_tab, make_recording, tmp_path):
    path = tmp_path / "band.toml"
    templates.write_template(
        path,
        templates.LogTemplate(
            channels=(
                templates.TemplateChannel(index=0, band="S", fc_mhz="433"),
                templates.TemplateChannel(index=1, fc_mhz="1575.42"),
            )
        ),
    )
    tab = make_tab()
    scan_folder(qtbot, tab, make_recording(n_channels=2).root)
    tab.import_template(path)
    assert (band_text(tab, 0), band_text(tab, 1)) == ("S", "L")
    assert not is_italic(tab.channel_widgets(0)[0])
    assert is_italic(tab.channel_widgets(1)[0])


def test_edit_mode_shows_the_stored_band(qtbot, make_tab, make_recording, site_id, db_path):
    info = make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, info, site_id)
    type_band(qtbot, tab, "UHF")  # against fc 145.8, as in the 1.1.1 manual test
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    band, fc, _fs = tab.channel_widgets(0)
    assert (band.currentText(), fc.text()) == ("UHF", "145.8")
    assert not is_italic(band)
    assert outside_lines(tab) == [
        "Channel 0: fc 145.8 MHz is outside UHF (300 to 1000 MHz). Check the band."
    ]
    save_and_wait(qtbot, tab)
    assert tab.message_text == "No changes to save."
    type_band(qtbot, tab, "")
    qtbot.keyClicks(fc, "0")  # 145.80: the empty band follows the typed fc
    assert band.currentText() == "VHF"


# ---------------------------------------------------------------------------
# Templates (D80)
# ---------------------------------------------------------------------------


@pytest.fixture
def project_id(db_path) -> int:
    return entry.add_project(db_path, "Radar Trial").id


def filled_tab(qtbot, make_tab, make_recording, site_id, project_id) -> LogTab:
    """A tab with a scanned two-channel folder and every typed field filled in."""
    tab = make_tab()
    scan_folder(qtbot, tab, make_recording(n_channels=2).root)
    fill_channels(tab)
    choose_site(tab, site_id)
    tab._select_project(project_id)
    tab.logged_by_edit.setText("userA")
    tab.plan_edit.setText("plan-9")
    tab.remarks_edit.setPlainText("USRP set-up")
    tab.layout_combo.setCurrentIndex(tab.layout_combo.findData(IqLayout.PLANAR_IQ))
    tab.param_table.add_row(entry.ParamInput(param="SDR", value="USRP B210"))
    tab.param_table.add_row(entry.ParamInput(param="Antenna", value="Yagi", channel_index=1))
    return tab


def typed_fields(tab: LogTab) -> tuple:
    form = tab.current_input()
    return (
        form.logged_by,
        form.site_id,
        form.project_id,
        form.recording_plan_ref,
        form.remarks,
        str(form.dtype),
        str(form.iq_layout),
        str(form.endianness),
        form.header_bytes,
        [(c.channel_index, c.band, c.fc_mhz) for c in form.channels],
        form.params,
    )


def test_export_then_import_gives_the_same_form(
    qtbot, make_tab, make_recording, site_id, project_id, tmp_path
):
    tab = filled_tab(qtbot, make_tab, make_recording, site_id, project_id)
    before = typed_fields(tab)
    path = tmp_path / "templates" / "usrp.toml"
    path.parent.mkdir()
    tab.export_template(path, set(templates.TemplateField))
    assert tab.message_text == f"Template saved: {path}"
    tab.clear_form()
    scan_folder(qtbot, tab, make_recording(n_channels=2).root)
    tab.import_template(path)
    assert typed_fields(tab) == before
    assert tab.message_text.startswith("Template loaded: Logged by, Site, Project")
    fs = tab.channel_widgets(0)[2]
    assert fs.text() == "1 kHz"  # from the scan, not from the template


def test_export_of_some_fields_imports_only_those(
    qtbot, make_tab, make_recording, site_id, project_id, tmp_path
):
    tab = filled_tab(qtbot, make_tab, make_recording, site_id, project_id)
    path = tmp_path / "rf.toml"
    tab.export_template(path, {templates.TemplateField.RF_CHAIN})
    tab.clear_form()
    tab.plan_edit.setText("plan-10")
    tab.import_template(path)
    assert [p.param for p in tab.param_table.rows()] == ["SDR", "Antenna"]
    assert tab.plan_edit.text() == "plan-10"
    assert tab.site_combo.currentData() is None
    assert tab.layout_combo.currentData() == IqLayout.INTERLEAVED_IQ


def test_import_before_a_scan_fills_the_channels_when_the_scan_ends(
    qtbot, make_tab, make_recording, tmp_path
):
    path = tmp_path / "vhf.toml"
    templates.write_template(
        path,
        templates.LogTemplate(
            sample_type=SampleType.INT16,
            channels=(templates.TemplateChannel(index=1, band="UHF", fc_mhz="435"),),
        ),
    )
    tab = make_tab()
    tab.import_template(path)
    scan_folder(qtbot, tab, make_recording(n_channels=2).root)
    assert tab.channel_widgets(1)[0].currentText() == "UHF"
    assert tab.channel_widgets(1)[1].text() == "435"
    assert tab.channel_widgets(0)[1].text() == ""


def test_import_names_a_site_the_catalogue_lacks(qtbot, make_tab, site_id, tmp_path):
    path = tmp_path / "site.toml"
    templates.write_template(path, templates.LogTemplate(site="Hilltop", logged_by="userB"))
    tab = make_tab()
    choose_site(tab, site_id)
    tab.import_template(path)
    assert tab.site_combo.currentData() == site_id
    assert tab.logged_by_edit.text() == "userB"
    assert "Site 'Hilltop' is not in the catalogue." in tab.message_text


def test_a_wrong_template_changes_nothing(qtbot, make_tab, tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('format_version = 1\nsample_type = "int12"\n', encoding="utf-8")
    tab = make_tab()
    tab.import_template(path)
    assert tab.message_text.startswith("Template not loaded: 'sample_type'")
    assert tab.dtype_combo.currentData() == SampleType.INT16


def test_the_export_dialog_starts_with_empty_fields_unticked(qtbot, make_tab, site_id):
    tab = make_tab()
    choose_site(tab, site_id)
    tab.param_table.add_row(entry.ParamInput(param="SDR", value="X310"))
    rows = {field: (text, ticked) for field, text, ticked in tab.template_field_rows()}
    field = templates.TemplateField
    assert rows[field.SITE] == ("Site: SiteA", True)
    assert rows[field.PROJECT] == (f"Project: {NO_PROJECT}", False)
    assert rows[field.PLAN] == ("Recording plan reference: empty", False)
    assert rows[field.CHANNELS] == ("Band and fc of each channel: 0 channels", False)
    assert rows[field.RF_CHAIN] == ("RF chain: 1 row", True)
    assert rows[field.FORMAT][1] is True

    dialog = TemplateFieldsDialog(tab.template_field_rows())
    qtbot.addWidget(dialog)
    ok = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
    assert field.SITE in dialog.chosen()
    for box in dialog.boxes.values():
        box.setChecked(False)
    assert not ok.isEnabled()  # at least one field


def test_export_asks_before_it_replaces_a_template(qtbot, make_tab, tmp_path, monkeypatch):
    path = tmp_path / "usrp.toml"
    templates.write_template(path, templates.LogTemplate(site="Lab"))
    tab = make_tab()
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **kw: (str(tmp_path / "usrp"), "")
    )
    asked = []

    def question(parent, title, text, *args):
        asked.append((title, text))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", question)
    tab.export_template(fields={templates.TemplateField.FORMAT})
    assert asked == [(REPLACE_TEMPLATE_TITLE, replace_template_question(path))]
    assert templates.read_template(path) == templates.LogTemplate(site="Lab")
    assert tab.message_text == "Template not saved."


# ---------------------------------------------------------------------------
# Light and dark themes (second manual test, 2026-10-02)
# ---------------------------------------------------------------------------


def luminance(colour: QColor) -> float:
    """Relative luminance as defined for WCAG contrast."""

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(colour.redF())
        + 0.7152 * channel(colour.greenF())
        + 0.0722 * channel(colour.blueF())
    )


def contrast(a: QColor, b: QColor) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def themed_palette(base: str, text: str, window: str) -> QPalette:
    palette = QPalette()
    for role, colour in (
        (QPalette.ColorRole.Base, base),
        (QPalette.ColorRole.Text, text),
        (QPalette.ColorRole.Window, window),
        (QPalette.ColorRole.WindowText, text),
    ):
        palette.setColor(role, QColor(colour))
    return palette


DARK = themed_palette("#2d2d2d", "#ffffff", "#202020")  # Windows 11 dark, approximately
LIGHT = themed_palette("#ffffff", "#000000", "#f0f0f0")


@pytest.fixture
def app_palette(qapp):
    """Set the application palette in a test and restore it afterwards."""
    before = qapp.palette()
    yield qapp.setPalette
    qapp.setPalette(before)


def field_colours(edit) -> tuple[QColor, QColor]:
    palette = edit.palette()
    return palette.color(QPalette.ColorRole.Base), palette.color(QPalette.ColorRole.Text)


@pytest.mark.parametrize("theme", [DARK, LIGHT], ids=["dark", "light"])
def test_fields_are_readable_in_both_themes(make_tab, app_palette, theme):
    app_palette(theme)
    tab = make_tab()
    base, text = field_colours(tab.folder_edit)
    assert base == theme.color(QPalette.ColorRole.Base)
    assert text == theme.color(QPalette.ColorRole.Text)
    for field in (tab.start_edit, tab.storage_root_edit, tab.rel_path_edit, tab.state_edit):
        ro_base, ro_text = field_colours(field)
        assert contrast(ro_text, ro_base) >= 4.5
        assert ro_base != base


def test_fields_follow_a_theme_switch(make_tab, app_palette, qapp):
    app_palette(LIGHT)
    tab = make_tab()
    light_ro = field_colours(tab.start_edit)
    app_palette(DARK)
    qapp.processEvents()
    dark_ro = field_colours(tab.start_edit)
    assert dark_ro != light_ro
    assert dark_ro[0].lightnessF() < 0.5
    assert contrast(dark_ro[1], dark_ro[0]) >= 4.5
    assert field_colours(tab.folder_edit) == (QColor("#2d2d2d"), QColor("#ffffff"))


@pytest.mark.parametrize(
    ("colours", "background"),
    [(LIGHT_COLOURS, "#ffffff"), (DARK_COLOURS, "#2d2d2d")],
    ids=["light", "dark"],
)
def test_checklist_colours_have_enough_contrast(colours, background):
    for state, colour in colours.items():
        assert contrast(colour, QColor(background)) >= 4.5, state


def test_checklist_switches_colours_with_the_theme(make_tab, app_palette, qapp):
    app_palette(LIGHT)
    tab = make_tab()
    assert tab.checklist.item(0).foreground().color() == LIGHT_COLOURS[ItemState.TODO]
    app_palette(DARK)
    qapp.processEvents()
    assert tab.checklist.item(0).foreground().color() == DARK_COLOURS[ItemState.TODO]


# ---------------------------------------------------------------------------
# Folder named like a channel folder (DECISIONS.md D27)
# ---------------------------------------------------------------------------


def test_channel_folder_warning_and_use_parent(qtbot, make_tab, make_recording, site_id):
    info = make_recording(n_channels=2)
    tab = make_tab()
    tab.folder_edit.setText(str(Path(info.root, "0")))
    assert tab.use_parent_button.isVisibleTo(tab)
    infos = checklist_texts(tab, ItemState.INFO)
    assert any(t.startswith("This folder is named like a channel folder.") for t in infos)
    tab.use_parent_button.click()
    assert Path(tab.folder_edit.text()) == Path(info.root)
    assert not tab.use_parent_button.isVisibleTo(tab)
    scan_folder(qtbot, tab, tab.folder_edit.text())
    assert tab.channel_table.rowCount() == 2


def test_channel_folder_warning_does_not_block_saving(qtbot, make_tab, make_recording, site_id):
    info = make_recording(n_channels=2)
    tab = make_tab()
    logged_ready(qtbot, tab, type("Info", (), {"root": str(Path(info.root, "0"))}), site_id)
    assert entry.can_save(tab.checklist.items), checklist_texts(tab)
    assert tab.save_button.isEnabled()


def test_no_channel_folder_warning_for_a_normal_folder(make_tab, make_recording):
    info = make_recording()
    tab = make_tab()
    tab.folder_edit.setText(info.root)
    tab.refresh_checklist()
    assert not tab.use_parent_button.isVisibleTo(tab)


def test_rf_chain_names_take_the_stored_spelling(qtbot, make_tab, make_recording, db_path, site_id):
    """DECISIONS.md D28: the tab passes the names in the database to the checklist and save."""
    first, second = make_recording(), make_recording()
    tab = make_tab()
    logged_ready(qtbot, tab, first, site_id)
    tab.param_table.add_row(entry.ParamInput(param="LNA gain", value="20", unit="dB"))
    save_and_wait(qtbot, tab)
    assert tab._choices.param_names == ["LNA gain"]

    logged_ready(qtbot, tab, second, site_id)
    tab.param_table.set_rows([])  # the row kept from the first entry (D79)
    tab.param_table.add_row(entry.ParamInput(param="lna GAIN", value="25", unit="dB"))
    assert "lna GAIN will be saved as LNA gain, the spelling already in use." in (
        checklist_texts(tab, ItemState.INFO)
    )
    save_and_wait(qtbot, tab)
    assert entry.load_recording(db_path, 2).params[0].param == "LNA gain"


# ---------------------------------------------------------------------------
# New configuration from the Settings tab (Milestone 3a, O28)
# ---------------------------------------------------------------------------


def header_texts(tab: LogTab) -> list[str]:
    table = tab.channel_table
    return [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]


def test_offset_change_redraws_times_and_keeps_the_form(qtbot, make_tab, make_recording, db_path):
    info = make_recording(n_channels=2)
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    fill_channels(tab, fc_mhz="433.92")
    tab.remarks_edit.setPlainText("keep me")
    start = tab.scan.channels[0].start_unix
    assert tab.start_edit.text() == time_text(start, 8.0)

    new = replace(tab.config, display_utc_offset_hours=0.0)
    assert not tab.apply_clears_form(new)
    tab.apply_config(new)
    wait_idle(qtbot, tab)
    assert tab.start_label.text() == "Start (UTC) · from scan"
    assert tab.end_label.text() == "End (UTC) · from scan"
    assert header_texts(tab) == list(channel_headers("UTC"))
    assert tab.start_edit.text() == time_text(start, 0.0)
    assert tab.channel_table.item(0, 5).text() == time_text(start, 0.0)
    assert tab.scan_summary.text() == scan_summary(tab.scan, 0.0)
    assert tab.folder_edit.text() == info.root
    assert tab.remarks_edit.toPlainText() == "keep me"
    assert tab.channel_widgets(1)[1].text() == "433.92"
    assert tab.config.display_utc_offset_hours == 0.0


def test_offset_change_in_edit_mode_keeps_typed_values(qtbot, make_tab, make_recording, site_id):
    info = make_recording(n_channels=2)
    tab = saved_tab(qtbot, make_tab, info, site_id)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    tab.channel_widgets(1)[1].setText("433.92")
    tab.apply_config(replace(tab.config, display_utc_offset_hours=5.5))
    wait_idle(qtbot, tab)
    assert tab.editing is not None
    assert tab.start_edit.text() == time_text(tab.editing.start_unix, 5.5)
    assert tab.channel_widgets(1)[1].text() == "433.92"
    assert header_texts(tab) == list(channel_headers("UTC+5:30"))


def test_new_database_clears_the_form_and_loads_its_lists(
    qtbot, make_tab, make_recording, site_id, tmp_path
):
    other = tmp_path / "other.db"
    create_database(other)
    other_site = entry.add_site(other, "Elsewhere")
    info = make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    choose_site(tab, site_id)
    new = replace(tab.config, db_path=str(other))
    assert tab.apply_clears_form(new)
    tab.apply_config(new)
    wait_idle(qtbot, tab)
    assert tab.folder_edit.text() == ""
    assert tab.scan is None
    sites = [tab.site_combo.itemData(i) for i in range(tab.site_combo.count())]
    assert sites == [other_site.id]
    assert tab.site_combo.currentIndex() == -1
    assert tab.config.db_path == str(other)


def test_removing_the_database_path_disables_save(qtbot, make_tab, make_recording, site_id):
    tab = make_tab()
    tab.apply_config(Config())
    wait_idle(qtbot, tab)
    assert tab.site_combo.count() == 0
    assert "No database configured" in tab.message_text
    assert not tab.save_button.isEnabled()


def test_new_nas_roots_clear_the_form(qtbot, make_tab, make_recording):
    info = make_recording()
    tab = make_tab()
    scan_folder(qtbot, tab, info.root)
    new = replace(tab.config, nas_roots=(NAS,))
    assert tab.apply_clears_form(new)
    tab.apply_config(new)
    wait_idle(qtbot, tab)
    assert tab.folder_edit.text() == ""
    assert tab.config.nas_roots == (NAS,)


def test_lists_from_the_old_database_are_dropped(qtbot, make_tab, site_id, tmp_path):
    other = tmp_path / "other.db"
    create_database(other)
    tab = make_tab()
    tab.reload_choices()  # still loading from the first database
    tab.apply_config(replace(tab.config, db_path=str(other)))
    wait_idle(qtbot, tab)
    assert tab.site_combo.count() == 0


def test_has_unsaved_input(qtbot, make_tab, make_recording, site_id):
    tab = make_tab()
    assert not tab.has_unsaved_input()
    tab.plan_edit.setText("plan 7")
    assert tab.has_unsaved_input()
    tab.clear_form()
    tab.remarks_edit.setPlainText("note")
    assert tab.has_unsaved_input()
    tab.clear_form()
    tab.param_table.add_row(entry.ParamInput(param="", value=""))
    assert not tab.has_unsaved_input()  # an empty row holds nothing
    tab.param_table.row_widgets(0)[2].setText("30")
    assert tab.has_unsaved_input()
    tab.clear_form()
    tab.folder_edit.setText(make_recording().root)
    assert tab.has_unsaved_input()
    tab.clear_form()
    assert not tab.has_unsaved_input()


def test_edit_mode_counts_as_unsaved_input(qtbot, make_tab, make_recording, site_id):
    tab = saved_tab(qtbot, make_tab, make_recording(n_channels=2), site_id)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert tab.has_unsaved_input()
    assert not tab.is_saving


# ---------------------------------------------------------------------------
# The message line shows its state (D84)
# ---------------------------------------------------------------------------


def shown(tab: LogTab) -> tuple[str, str]:
    """The message line's text as shown, and its colour."""
    return tab.message_label.text(), tab.message_label.styleSheet()


@pytest.mark.parametrize("theme", [DARK, LIGHT], ids=["dark", "light"])
def test_messages_show_their_mark_and_colour(
    qtbot, make_tab, make_recording, site_id, tmp_path, app_palette, theme
):
    app_palette(theme)
    colours = DARK_COLOURS if theme is DARK else LIGHT_COLOURS
    tab = make_tab()
    logged_ready(qtbot, tab, make_recording(), site_id)
    save_and_wait(qtbot, tab)
    ok = f"color: {colours[ItemState.OK].name()};"
    assert shown(tab) == ("\N{CHECK MARK}  Saved as recording 1.", ok)
    assert tab.message_state is ItemState.OK

    unknown = tmp_path / "unknown.toml"
    templates.write_template(unknown, templates.LogTemplate(site="Hilltop"))
    tab.import_template(unknown)
    text, style = shown(tab)
    assert text.startswith(f"{MARKS[ItemState.INFO]}  Template loaded: Site.")
    assert style == f"color: {colours[ItemState.INFO].name()};"

    broken = tmp_path / "broken.toml"
    broken.write_text('format_version = 1\nsampletype = "int8"\n', encoding="utf-8")
    tab.import_template(broken)
    text, style = shown(tab)
    assert text == (
        f"{MARKS[ItemState.ERROR]}  Template not loaded: "
        "Unknown entry in the template: sampletype."
    )
    assert style == f"color: {colours[ItemState.ERROR].name()};"


def test_the_message_colour_follows_a_theme_switch(qtbot, make_tab, app_palette):
    app_palette(LIGHT)
    tab = make_tab()
    tab.show_message("Choose a folder first.", ItemState.TODO)
    assert shown(tab)[1] == f"color: {LIGHT_COLOURS[ItemState.TODO].name()};"
    app_palette(DARK)  # the change reaches the tab as an event
    dark = f"color: {DARK_COLOURS[ItemState.TODO].name()};"
    qtbot.waitUntil(lambda: shown(tab)[1] == dark, timeout=2_000)


def test_a_message_without_a_state_is_plain(make_tab):
    tab = make_tab()
    tab.show_message("Saving...")
    assert shown(tab) == ("Saving...", "")
    assert tab.message_text == "Saving..."


# ---------------------------------------------------------------------------
# Deleting an entry added by mistake (D89)
# ---------------------------------------------------------------------------


@pytest.fixture
def delete_answer(monkeypatch):
    """Replace the question: record its text and give a set answer."""
    asked: list[str] = []
    answer = {"delete": True}

    def confirm(parent, text):
        asked.append(text)
        return answer["delete"]

    monkeypatch.setattr(log_tab_module, "confirm_delete", confirm)
    return asked, answer


def opened_for_edit(qtbot, make_tab, info, site_id, **kw) -> LogTab:
    """A saved entry, open in edit mode as recording 1."""
    tab = make_tab(**kw)
    logged_ready(qtbot, tab, info, site_id)
    save_and_wait(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert tab.editing is not None
    return tab


def delete_and_wait(qtbot, tab: LogTab) -> None:
    tab.delete_button.click()
    wait_idle(qtbot, tab)
    wait_idle(qtbot, tab)  # the check, then the delete


def test_the_delete_button_shows_in_edit_mode_only(
    qtbot, make_tab, make_recording, site_id, tmp_path
):
    tab = opened_for_edit(qtbot, make_tab, make_recording(), site_id, records_folder=tmp_path)
    assert not tab.delete_button.isHidden()
    assert tab.delete_button.isEnabled()
    tab.clear_form()
    assert tab.delete_button.isHidden()


def test_delete_clears_the_form_and_says_so(
    qtbot, make_tab, make_recording, site_id, db_path, tmp_path, delete_answer
):
    asked, _ = delete_answer
    info = make_recording()
    before = sorted((p.name, p.stat().st_size) for p in Path(info.root).rglob("*"))
    records = tmp_path / "deleted-entries"
    tab = opened_for_edit(qtbot, make_tab, info, site_id, records_folder=records)
    with qtbot.waitSignal(tab.deleted) as signal:
        delete_and_wait(qtbot, tab)
    assert signal.args == [1]
    (question,) = asked
    assert question.startswith("Delete recording 1 from the catalogue?")
    (record,) = records.iterdir()
    assert tab.message_state is ItemState.OK
    assert tab.message_text == (
        "Deleted recording 1 from the catalogue. Its files were not touched. "
        f"A copy of the entry is in {record}."
    )
    assert tab.editing is None
    assert tab.mode_label.text() == "New entry"
    with open_db(db_path, readonly=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 0
    assert sorted((p.name, p.stat().st_size) for p in Path(info.root).rglob("*")) == before


def test_cancel_deletes_nothing(
    qtbot, make_tab, make_recording, site_id, db_path, tmp_path, delete_answer
):
    _, answer = delete_answer
    answer["delete"] = False
    records = tmp_path / "deleted-entries"
    tab = opened_for_edit(qtbot, make_tab, make_recording(), site_id, records_folder=records)
    delete_and_wait(qtbot, tab)
    assert (tab.message_state, tab.message_text) == (ItemState.INFO, "Nothing deleted.")
    assert tab.editing is not None
    assert not records.exists()
    with open_db(db_path, readonly=True) as conn:
        assert repository.get_recording(conn, 1).id == 1


def test_an_archived_or_copied_entry_is_not_deleted(
    qtbot, make_tab, make_recording, site_id, db_path, tmp_path, delete_answer
):
    asked, _ = delete_answer
    tab = opened_for_edit(qtbot, make_tab, make_recording(), site_id, records_folder=tmp_path)
    write_transaction(
        db_path,
        lambda conn: repository.insert_transfer(
            conn,
            TransferEntry(
                recording_id=1,
                operation=Operation.COPY,
                source="C:/rec",
                destination="D:/work/rec",
                started_at="2026-10-23T08:00:00Z",
                performed_by="u",
            ),
        ),
    )
    delete_and_wait(qtbot, tab)
    assert asked == []
    assert tab.message_state is ItemState.ERROR
    assert tab.message_text == (
        "Not deleted: Recording 1 has an archive or a copy in its history, so it cannot be "
        "deleted. Correct it with Save entry instead."
    )
    assert tab.editing is not None


def test_a_recording_another_tab_holds_is_not_deleted(
    qtbot, make_tab, make_recording, site_id, tmp_path, delete_answer
):
    asked, _ = delete_answer
    held = "The Archive / copy queue holds recording 1."
    tab = opened_for_edit(
        qtbot,
        make_tab,
        make_recording(),
        site_id,
        records_folder=tmp_path,
        deletion_blocked=lambda rid: held if rid == 1 else None,
    )
    tab.delete_button.click()
    assert not tab.runner.busy
    assert (tab.message_state, tab.message_text) == (ItemState.ERROR, held)
    assert asked == []


def test_without_a_records_folder_nothing_is_deleted(
    qtbot, make_tab, make_recording, site_id, delete_answer
):
    tab = opened_for_edit(qtbot, make_tab, make_recording(), site_id)
    tab.delete_button.click()
    assert tab.message_text == log_tab_module.NO_RECORDS_FOLDER
    assert tab.editing is not None


def test_a_save_over_an_entry_deleted_elsewhere(
    qtbot, make_tab, make_recording, site_id, db_path, tmp_path
):
    tab = opened_for_edit(qtbot, make_tab, make_recording(), site_id)
    original = tab.editing
    check = entry.check_deletion(db_path, original)
    entry.delete_entry(db_path, check, records_folder=tmp_path, deleted_by="other")
    tab.plan_edit.setText("plan-2")
    save_and_wait(qtbot, tab)
    assert tab.message_state is ItemState.ERROR
    assert tab.message_text == (
        "Not saved: Recording 1 is no longer in the catalogue. It may have been deleted on "
        "another PC."
    )
