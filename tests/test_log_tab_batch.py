"""The Log tab's "Several folders" mode (DECISIONS.md D90).

Synthetic recordings under tmp_path, a fresh database, and stubs for every question.
"""

import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import iqdm.gui.log_tab as log_tab_module
import make_fixtures
from conftest import recorder_log_text
from iqdm import batchlog, entry, templates
from iqdm.config import Config
from iqdm.db import repository
from iqdm.db.connection import open_db
from iqdm.entry import ItemState
from iqdm.gui.log_tab import LogTab
from iqdm.models import SampleType
from iqdm.scan.scanner import ScanCancelled
from make_fixtures import RecordingSpec

T0 = make_fixtures.DEFAULT_START_UNIX


@pytest.fixture(autouse=True)
def popups(monkeypatch) -> list[tuple[str, str]]:
    shown: list[tuple[str, str]] = []

    def information(parent, title, text, *a):
        shown.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", information)
    return shown


@pytest.fixture(autouse=True)
def no_unexpected_question(monkeypatch):
    """A real question would block the run. A test that expects one replaces this stub."""

    def question(parent, title, text, *a):
        raise AssertionError(f"unexpected question: {text}")

    monkeypatch.setattr(QMessageBox, "question", question)


@pytest.fixture
def save_answer(monkeypatch):
    """Replace the save question: record its text and give a set answer."""
    asked: list[str] = []
    answer = {"save": True}

    def confirm(parent, text):
        asked.append(text)
        return answer["save"]

    monkeypatch.setattr(log_tab_module, "confirm_batch_save", confirm)
    return asked, answer


@pytest.fixture
def site_id(db_path) -> int:
    return entry.add_site(db_path, "SiteA").id


@pytest.fixture
def tab(qtbot, db_path):
    t = LogTab(Config(db_path=str(db_path)))
    qtbot.addWidget(t)
    wait_idle(qtbot, t)
    yield t
    t.cancel_scan()
    t._cancel_batch_task()
    t.runner.wait(10_000)


def wait_idle(qtbot, tab: LogTab) -> None:
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=20_000)


def recording(parent: Path, name: str, *, log=None, start=T0, **kw) -> Path:
    info = make_fixtures.make_recording(parent / name, RecordingSpec(start_unix=start, **kw))
    root = Path(info.root)
    if log is not None:
        (root / f"recorder_{root.name}.log").write_text(recorder_log_text(log), encoding="utf-8")
    return root


def session(tmp_path: Path) -> Path:
    """Two recordings an hour apart with logs, listed in the reverse order of time."""
    parent = tmp_path / "session"
    recording(parent, "a-late", start=T0 + 3600, log={0: (433.0, 30.0)})
    recording(parent, "b-early", log={0: (145.8, 20.0)})
    return parent


def test_the_band_column_follows_the_channel_order(qtbot, tab, tmp_path):
    parent = tmp_path / "session"
    recording(parent, "rec", n_channels=2, log={0: (433.0, 30.0), 1: (145.8, 30.0)})
    several(qtbot, tab, parent)
    assert table_column(tab, "band") == ["UHF, VHF"]
    assert tab.source_box.title() == "1 · Source folders"


def several(qtbot, tab: LogTab, parent: Path) -> None:
    tab.several_radio.setChecked(True)
    tab.add_folders(parent)
    wait_idle(qtbot, tab)
    wait_idle(qtbot, tab)
    tab.refresh_checklist()


def ready(tab: LogTab, site_id: int) -> None:
    """Choose the site and a logged-by name. The site was added after the tab loaded."""
    tab.reload_choices(select_site=site_id)
    tab.runner.wait(10_000)
    QApplication.processEvents()
    assert tab.site_combo.currentData() == site_id
    tab.logged_by_edit.setText("userA")
    tab.refresh_checklist()


def texts(items, state: ItemState | None = None) -> list[str]:
    return [i.text for i in items if state is None or i.state is state]


def table_column(tab: LogTab, attr: str) -> list[str]:
    return [getattr(r, attr) for r in tab.folder_table.rows]


def test_the_mode_switch_shows_the_folder_list(qtbot, tab):
    assert tab.one_page.isVisibleTo(tab) and not tab.several_page.isVisibleTo(tab)
    tab.several_radio.setChecked(True)
    assert tab.batch_mode
    assert tab.several_page.isVisibleTo(tab) and not tab.one_page.isVisibleTo(tab)
    assert not tab.duration_spin.isEnabled()
    assert texts(tab.checklist.items) == ["Add folders, then scan them"]
    assert tab.save_button.text() == "Save entries"
    assert not tab.save_button.isEnabled()
    tab.one_radio.setChecked(True)  # an empty list asks nothing
    assert not tab.batch_mode
    assert tab.save_button.text() == "Save entry"


def test_folders_are_added_scanned_and_sorted_by_start(qtbot, tab, tmp_path):
    several(qtbot, tab, session(tmp_path))
    assert table_column(tab, "folder") == ["b-early", "a-late"]
    assert table_column(tab, "fc") == ["145.8", "433"]
    assert table_column(tab, "band") == ["VHF", "UHF"]
    assert table_column(tab, "dtype") == ["int16", "int16"]
    assert tab.batch_line.text() == "Scanned 2 folders."
    assert texts(tab.checklist.items, ItemState.TODO) == ["Choose a site (all 2 folders)"]


def test_save_saves_each_folder_with_the_shared_fields(
    qtbot, tab, tmp_path, site_id, db_path, save_answer
):
    asked, _ = save_answer
    several(qtbot, tab, session(tmp_path))
    ready(tab, site_id)
    tab.remarks_edit.setPlainText("Hilltop mast")
    tab.refresh_checklist()
    assert tab.save_button.isEnabled()
    assert tab.save_button.text() == "Save 2 entries"
    with qtbot.waitSignal(tab.saved) as signal:
        tab.save()
        wait_idle(qtbot, tab)
    (question,) = asked
    assert question.startswith("Save 2 entries?")
    assert (tab.message_state, tab.message_text) == (
        ItemState.OK,
        "Saved 2 entries (recordings 1 to 2).",
    )
    assert signal.args == [2]
    assert table_column(tab, "state_text") == ["Saved as recording 1", "Saved as recording 2"]
    assert not tab.save_button.isEnabled()
    assert tab.unsaved_folders() == 0
    with open_db(db_path, readonly=True) as conn:
        first, second = repository.get_recording(conn, 1), repository.get_recording(conn, 2)
    assert first.channels[0].fc_hz == 145.8e6 and second.channels[0].fc_hz == 433e6
    assert first.remarks == second.remarks == "Hilltop mast"
    assert {(p.param, p.value) for p in first.params} >= {("USRP gain", "20")}
    assert {(p.param, p.value) for p in second.params} >= {("USRP gain", "30")}


def test_cancel_saves_nothing(qtbot, tab, tmp_path, site_id, db_path, save_answer):
    _, answer = save_answer
    answer["save"] = False
    several(qtbot, tab, session(tmp_path))
    ready(tab, site_id)
    tab.save()
    assert (tab.message_state, tab.message_text) == (ItemState.INFO, "Nothing saved.")
    with open_db(db_path, readonly=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 0


def test_a_folder_without_a_log_is_fixed_in_place(qtbot, tab, tmp_path, site_id):
    parent = tmp_path / "session"
    recording(parent, "a", log={0: (433.0, 30.0)})
    recording(parent, "b", start=T0 + 3600)
    several(qtbot, tab, parent)
    ready(tab, site_id)
    assert texts(tab.checklist.items, ItemState.TODO) == ["b: Enter fc (MHz) for channel 0"]
    b_key = tab.folder_table.rows[1].key
    tab.folder_table.select_key(b_key)
    tab.refresh_checklist()
    assert tab.folder_label.text() == "Selected folder: b"
    assert texts(tab.folder_checklist.items, ItemState.TODO) == ["Enter fc (MHz) for channel 0"]
    band, fc, fs = tab.channel_widgets(0)
    assert fs.text() == "1 kHz" and "italic" in fs.styleSheet()  # from the file size
    qtbot.keyClicks(fc, "2400")
    assert band.currentText() == "S"
    tab.folder_table.select_key(tab.folder_table.rows[0].key)
    assert tab.channel_widgets(0)[1].text() == "433"
    tab.folder_table.select_key(b_key)
    assert tab.channel_widgets(0)[1].text() == "2400"  # kept for that folder
    tab.refresh_checklist()
    assert texts(tab.checklist.items, ItemState.TODO) == []
    assert tab.save_button.text() == "Save 2 entries"


def test_an_unticked_folder_is_left_out(qtbot, tab, tmp_path, site_id, save_answer):
    asked, _ = save_answer
    several(qtbot, tab, session(tmp_path))
    ready(tab, site_id)
    key = tab.folder_table.rows[1].key
    tab._tick_folder(key, False)
    tab.refresh_checklist()
    assert tab.save_button.text() == "Save 1 entry"
    tab.save()
    wait_idle(qtbot, tab)
    assert "Not saved now, unticked or not ready: a-late." in asked[0]
    assert tab.unsaved_folders() == 1


def test_an_already_logged_folder_starts_unticked(qtbot, tab, tmp_path, site_id, save_answer):
    parent = session(tmp_path)
    several(qtbot, tab, parent)
    ready(tab, site_id)
    tab.save()
    wait_idle(qtbot, tab)
    tab.one_radio.setChecked(True)  # every folder is saved: no question
    tab.several_radio.setChecked(True)
    tab.add_folders(parent)
    wait_idle(qtbot, tab)
    wait_idle(qtbot, tab)
    tab.refresh_checklist()
    assert table_column(tab, "ticked") == [False, False]
    assert table_column(tab, "state_text") == ["1 error", "1 error"]
    assert texts(tab.checklist.items) == ["Tick at least one folder to save"]


def test_a_folder_already_in_the_list_is_not_added_twice(qtbot, tab, tmp_path):
    parent = session(tmp_path)
    several(qtbot, tab, parent)
    tab.add_folders(parent)
    wait_idle(qtbot, tab)
    assert len(tab.folders) == 2
    assert tab.batch_line.text() == "Added 0 folders. 2 were already in the list."


def test_a_parent_that_is_a_recording_can_be_added_as_one(qtbot, tab, tmp_path):
    root = recording(tmp_path, "rec", n_channels=2, log={0: (300.0, 30.0), 1: (301.0, 30.0)})
    several(qtbot, tab, root)
    assert tab.folders == []
    assert tab.batch_line.text() == log_tab_module.PARENT_IS_RECORDING
    assert not tab.add_parent_button.isHidden()
    tab.add_parent_button.click()
    wait_idle(qtbot, tab)
    tab.refresh_checklist()
    assert table_column(tab, "folder") == ["rec"]
    assert table_column(tab, "fc") == ["300, 301"]
    assert table_column(tab, "band") == ["UHF"]  # one band, shown once
    assert tab.add_parent_button.isHidden()


def test_switching_back_asks_before_dropping_unsaved_folders(qtbot, tab, tmp_path, monkeypatch):
    answers = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    asked: list[str] = []

    def question(parent, title, text, *a):
        asked.append(text)
        return answers.pop(0)

    monkeypatch.setattr(QMessageBox, "question", question)
    several(qtbot, tab, session(tmp_path))
    tab.one_radio.setChecked(True)
    assert tab.batch_mode and len(tab.folders) == 2
    tab.one_radio.setChecked(True)
    assert not tab.batch_mode and tab.folders == []
    assert asked == [log_tab_module.drop_folders_question(2)] * 2


def test_a_template_sets_the_shared_fields_only(qtbot, tab, tmp_path, site_id):
    path = tmp_path / "set-up.toml"
    templates.write_template(
        path,
        templates.LogTemplate(
            site="SiteA",
            remarks="Hilltop mast",
            sample_type=SampleType.INT8,
            channels=(templates.TemplateChannel(index=0, band="S", fc_mhz="2400"),),
            rf_chain=(entry.ParamInput(param="Antenna", value="Yagi"),),
        ),
    )
    tab.reload_choices()
    wait_idle(qtbot, tab)
    several(qtbot, tab, session(tmp_path))
    tab.import_template(path)
    assert tab.remarks_edit.toPlainText() == "Hilltop mast"
    assert tab.site_combo.currentData() == site_id
    assert table_column(tab, "fc") == ["145.8", "433"]  # each folder's log
    assert table_column(tab, "dtype") == ["int16", "int16"]  # the logs' sc16
    assert tab.message_state is ItemState.INFO
    assert log_tab_module.BATCH_TEMPLATE_CHANNELS_NOTE in tab.message_text
    assert log_tab_module.BATCH_TEMPLATE_LOG_NOTE in tab.message_text


def test_edit_mode_leaves_the_folder_list(qtbot, tab, tmp_path, site_id, save_answer):
    several(qtbot, tab, session(tmp_path))
    ready(tab, site_id)
    tab.save()
    wait_idle(qtbot, tab)
    tab.load_recording(1)
    wait_idle(qtbot, tab)
    assert not tab.batch_mode
    assert tab.editing is not None and tab.editing.id == 1
    assert not tab.several_radio.isEnabled()


def test_cancel_stops_the_scan(qtbot, tab, tmp_path, monkeypatch):
    def waits_for_cancel(folder, **kw):
        while not kw["cancelled"]():
            time.sleep(0.01)
        raise ScanCancelled

    monkeypatch.setattr(batchlog, "scan_folder", waits_for_cancel)
    tab.several_radio.setChecked(True)
    tab.add_folders(session(tmp_path))
    qtbot.waitUntil(
        lambda: tab.batch_line.text().startswith("Scanning folder 1 of 2"), timeout=10_000
    )
    assert tab.cancel_folders_button.isEnabled()
    tab.cancel_folders_button.click()
    wait_idle(qtbot, tab)
    assert tab.batch_line.text() == "Scanned 0 folders. 2 not scanned."
    tab.refresh_checklist()
    assert "Scan the folders: 2 not scanned yet" in texts(tab.checklist.items, ItemState.TODO)
    assert table_column(tab, "state_text") == ["Not scanned", "Not scanned"]


def test_a_folder_logged_meanwhile_keeps_its_reason(
    qtbot, tab, tmp_path, site_id, db_path, save_answer
):
    several(qtbot, tab, session(tmp_path))
    ready(tab, site_id)
    built, _ = batchlog.build_recordings(tab._views)
    entry.save_new(db_path, built[1][1])  # another PC logs a-late first
    tab.save()
    wait_idle(qtbot, tab)
    assert tab.message_state is ItemState.INFO
    assert tab.message_text.startswith("Saved 1 entry (recording 2). 1 not saved: a-late: ")
    states = table_column(tab, "state_text")
    assert states[0] == "Saved as recording 2"
    assert states[1].startswith("Not saved: ")
    assert tab.unsaved_folders() == 1


def test_clear_form_empties_the_list(qtbot, tab, tmp_path):
    several(qtbot, tab, session(tmp_path))
    tab.clear_form()
    assert tab.batch_mode
    assert tab.folders == []
    assert not tab.has_unsaved_input()
