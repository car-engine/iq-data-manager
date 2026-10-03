"""GUI tests for the Settings tab (pytest-qt, offscreen). Files live in tmp_path.

Database checks run on a thread pool. Each test waits for the tab's TaskRunner to be
idle before it checks the status line.
"""

import sqlite3
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFileDialog, QInputDialog

from iqdm.config import Config, backup_path, load_config, read_config_data
from iqdm.db import version
from iqdm.db.connection import inspect_database
from iqdm.entry import ItemState
from iqdm.gui.settings_tab import (
    COVERAGE_MESSAGE,
    NO_CONFIG_PATH,
    NO_DB_PATH,
    OFFSET_MESSAGE,
    DatabaseStatus,
    SettingsTab,
    database_status,
    offset_preview,
)
from iqdm.gui.widgets.checklist import DARK_COLOURS, LIGHT_COLOURS, colours_for
from iqdm.models import HashMode

NAS = r"\\nas\recordings"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def wait_idle(qtbot, tab: SettingsTab) -> None:
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)


def set_user_version(path: Path, value: int) -> None:
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute(f"PRAGMA user_version = {value}")
    raw.close()


@pytest.fixture
def config_file(tmp_path) -> Path:
    """Where the tab reads and writes config.toml. The folder does not exist yet."""
    return tmp_path / "AppData" / "IQDataManager" / "config.toml"


@pytest.fixture
def make_tab(qtbot):
    tabs: list[SettingsTab] = []

    def _make(path: Path | None, **kw) -> SettingsTab:
        tab = SettingsTab(path, **kw)
        qtbot.addWidget(tab)
        tabs.append(tab)
        wait_idle(qtbot, tab)
        return tab

    yield _make
    for tab in tabs:
        tab.runner.wait(10_000)


@pytest.fixture
def replies(monkeypatch) -> list[tuple[str, bool]]:
    """Answers for QInputDialog.getText, used in order. A real dialog would block."""
    queue: list[tuple[str, bool]] = []

    def get_text(*args, **kwargs):
        return queue.pop(0)

    monkeypatch.setattr(QInputDialog, "getText", get_text)
    return queue


def roots(tab: SettingsTab) -> list[str]:
    return [tab.roots_list.item(i).text() for i in range(tab.roots_list.count())]


def save_and_get_config(qtbot, tab: SettingsTab) -> Config:
    with qtbot.waitSignal(tab.saved, timeout=5_000) as blocker:
        tab.save_button.click()
    wait_idle(qtbot, tab)
    return blocker.args[0]


# ---------------------------------------------------------------------------
# Status line text
# ---------------------------------------------------------------------------


TECHNICAL = ("schema", "journal", "busy timeout", "foreign keys", "user_version")


def plain(status: DatabaseStatus) -> bool:
    """The visible line holds no database internals (D38)."""
    return not any(word in status.line.lower() for word in TECHNICAL)


def test_status_for_a_current_database_is_green(db_path):
    status = database_status(inspect_database(db_path))
    assert status.state is ItemState.OK
    assert status.line == "\N{CHECK MARK} Connected. The database is ready to use."
    assert "Schema version 1 (this app expects 1)" in status.details
    assert "Journal mode delete, foreign keys on, busy timeout 5000 ms." in status.details
    assert str(db_path) in status.details


def test_status_for_an_older_database_is_red(db_path, monkeypatch):
    monkeypatch.setattr(version, "LATEST_VERSION", 2)
    status = database_status(inspect_database(db_path))
    assert status.state is ItemState.ERROR
    assert "older version of IQ Data Manager. This version cannot open it." in status.text
    assert "Schema version 1 (this app expects 2)" in status.details
    assert plain(status)


def test_status_for_a_newer_database_is_amber(db_path):
    set_user_version(db_path, 3)
    status = database_status(inspect_database(db_path))
    assert status.state is ItemState.INFO
    assert "You can view recordings but cannot save them." in status.text
    assert "Schema version 3 (this app expects 1)" in status.details
    assert plain(status)


def test_status_for_files_the_app_cannot_use_is_red(tmp_path):
    other = tmp_path / "other.db"
    raw = sqlite3.connect(other, autocommit=True)
    raw.execute("CREATE TABLE legacy (date TEXT)")
    raw.close()
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database" * 200)
    expected = {
        other: "This file is not an IQ Data Manager database.",
        junk: "This file is not an IQ Data Manager database.",
        tmp_path
        / "absent.db": "Database file not found. Check the path and the network connection.",
        tmp_path: "This path is a folder. Choose the database file.",
    }
    for path, text in expected.items():
        status = database_status(inspect_database(path))
        assert (status.state, status.text) == (ItemState.ERROR, text), path
        assert status.line.startswith("\N{BALLOT X} ")
        assert plain(status)
    assert "file is not a database" in database_status(inspect_database(junk)).details


def test_status_without_a_path_is_amber():
    assert NO_DB_PATH.state is ItemState.INFO
    assert NO_DB_PATH.line == (
        "\N{WHITE CIRCLE} No database chosen. Recordings cannot be saved until you choose one."
    )


@pytest.mark.parametrize(
    ("hours", "shown"),
    [
        (8.0, "2026-09-30 10:00:00 (UTC+8)"),
        (0.0, "2026-09-30 02:00:00 (UTC)"),
        (5.5, "2026-09-30 07:30:00 (UTC+5:30)"),
        (-3.75, "2026-09-29 22:15:00 (UTC-3:45)"),
    ],
)
def test_offset_preview(hours, shown):
    assert offset_preview(hours) == f"2026-09-30 02:00:00 UTC is shown as {shown}."


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_fields_show_the_file(make_tab, config_file, db_path):
    write(
        config_file,
        f"db_path = '{db_path}'\nnas_roots = ['{NAS}', '\\\\nas2\\iq']\n"
        "display_utc_offset_hours = 5.5\n",
    )
    tab = make_tab(config_file)
    assert tab.db_edit.text() == str(db_path)
    assert roots(tab) == [NAS, r"\\nas2\iq"]
    assert tab.offset_spin.value() == 5.5
    assert tab.offset_preview.text() == offset_preview(5.5)
    assert tab.db_status.text() == "\N{CHECK MARK} Connected. The database is ready to use."
    assert "Schema version 1" in tab.db_status.toolTip()
    assert not tab.save_button.isEnabled()
    assert tab.problem_label.isHidden()
    assert "Comments typed into the file by hand are not kept" in tab.file_note.text()


def test_missing_file_shows_the_defaults(make_tab, config_file):
    tab = make_tab(config_file)
    assert (tab.db_edit.text(), roots(tab), tab.offset_spin.value()) == ("", [], 8.0)
    assert tab.db_state == NO_DB_PATH
    assert tab.db_status.text() == NO_DB_PATH.line
    assert not tab.save_button.isEnabled()
    assert not tab.open_folder_button.isEnabled()  # the folder does not exist yet
    assert tab.config_path_label.text() == str(config_file)


def test_without_a_config_path_nothing_can_be_saved(make_tab):
    tab = make_tab(None)
    tab.db_edit.setText(r"D:\a.db")
    assert not tab.save_button.isEnabled()
    assert not tab.reload_button.isEnabled()
    assert not tab.open_folder_button.isEnabled()
    assert tab.problem_label.text() == NO_CONFIG_PATH
    tab.save()  # does nothing


def test_tab_never_changes_the_database(qtbot, make_tab, config_file, db_path):
    before = (db_path.read_bytes(), db_path.stat().st_mtime_ns)
    write(config_file, f"db_path = '{db_path}'")
    tab = make_tab(config_file)
    tab.check_button.click()
    wait_idle(qtbot, tab)
    assert (db_path.read_bytes(), db_path.stat().st_mtime_ns) == before
    assert sorted(p.name for p in db_path.parent.iterdir()) == ["AppData", "catalog.db"]


# ---------------------------------------------------------------------------
# Database checks
# ---------------------------------------------------------------------------


def test_check_connection_runs_the_check_again(qtbot, make_tab, config_file, db_path):
    write(config_file, f"db_path = '{db_path}'")
    tab = make_tab(config_file)
    assert tab.db_state.state is ItemState.OK
    set_user_version(db_path, 3)
    tab.check_button.click()
    wait_idle(qtbot, tab)
    assert tab.db_state.state is ItemState.INFO
    assert "newer version" in tab.db_status.text()


def test_a_typed_path_is_checked_when_editing_finishes(qtbot, make_tab, config_file, db_path):
    tab = make_tab(config_file)
    tab.db_edit.setText(str(db_path))
    tab.db_edit.editingFinished.emit()
    wait_idle(qtbot, tab)
    assert tab.db_state.state is ItemState.OK
    tab.db_edit.setText(str(db_path.parent / "absent.db"))
    tab.db_edit.editingFinished.emit()
    wait_idle(qtbot, tab)
    assert tab.db_state.state is ItemState.ERROR
    assert "Database file not found" in tab.db_status.text()


def test_a_check_in_progress_is_amber(qtbot, make_tab, config_file, db_path):
    tab = make_tab(config_file)
    tab.db_edit.setText(str(db_path))
    tab.check_button.click()
    assert tab.db_status.text() == "\N{WHITE CIRCLE} Checking the database..."
    assert tab.db_state.state is ItemState.INFO
    wait_idle(qtbot, tab)
    assert tab.db_state.state is ItemState.OK


def test_browse_sets_the_path_and_checks_it(qtbot, make_tab, config_file, db_path, monkeypatch):
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: (db_path.as_posix(), "SQLite database")
    )
    tab = make_tab(config_file)
    tab.db_browse_button.click()
    wait_idle(qtbot, tab)
    assert tab.db_edit.text() == str(db_path)
    assert tab.db_state.state is ItemState.OK
    assert tab.save_button.isEnabled()


def test_cancelled_browse_changes_nothing(make_tab, config_file, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    tab = make_tab(config_file)
    tab.db_browse_button.click()
    assert tab.db_edit.text() == ""
    assert tab.db_state == NO_DB_PATH


def test_a_late_result_of_an_earlier_check_is_dropped(make_tab, config_file):
    tab = make_tab(config_file)
    tab._checked(tab._check_id - 1, DatabaseStatus(ItemState.OK, "an old result"))
    assert tab.db_state == NO_DB_PATH


# ---------------------------------------------------------------------------
# NAS roots
# ---------------------------------------------------------------------------


def test_add_edit_and_remove_roots(make_tab, config_file, replies):
    tab = make_tab(config_file)
    assert not tab.edit_root_button.isEnabled()
    replies += [(f" {NAS} ", True), ("", True), (r"\\nas2\iq", False)]
    tab.add_root_button.click()
    tab.add_root_button.click()  # empty text adds nothing
    tab.add_root_button.click()  # cancelled
    assert roots(tab) == [NAS]
    assert tab.save_button.isEnabled()

    replies.append((r"\\nas\other", True))
    tab.roots_list.setCurrentRow(0)
    tab.edit_root_button.click()
    assert roots(tab) == [r"\\nas\other"]

    tab.remove_root_button.click()
    assert roots(tab) == []
    assert not tab.remove_root_button.isEnabled()
    assert not tab.save_button.isEnabled()  # back to the file's value


def test_a_wrong_root_is_marked_and_blocks_save(make_tab, config_file, replies):
    tab = make_tab(config_file)
    replies.append((r"D:\data", True))
    tab.add_root_button.click()
    item = tab.roots_list.item(0)
    message = r"D:\data is not a network location. Use the form \\server\share."
    assert item.toolTip() == message
    assert item.foreground().color() == colours_for(tab.palette())[ItemState.ERROR]
    assert tab.roots_error.isVisibleTo(tab)
    assert tab.roots_error.text() == message
    assert not tab.save_button.isEnabled()

    replies.append((NAS, True))
    tab.edit_root_button.click()
    assert item.toolTip() == ""
    assert not tab.roots_error.isVisibleTo(tab)
    assert tab.save_button.isEnabled()


def test_a_wrong_root_in_the_file_can_be_corrected(make_tab, config_file, replies):
    write(config_file, r"nas_roots = ['D:\data']")
    tab = make_tab(config_file)
    assert roots(tab) == [r"D:\data"]
    assert "Correct the field marked in red" in tab.problem_label.text()
    assert "not a UNC path" in tab.problem_label.toolTip()  # the technical text
    assert "network location" in tab.roots_error.text()
    assert not tab.save_button.isEnabled()
    replies.append((NAS, True))
    tab.roots_list.setCurrentRow(0)
    tab.edit_root_button.click()
    assert tab.save_button.isEnabled()


# ---------------------------------------------------------------------------
# Display offset
# ---------------------------------------------------------------------------


def test_preview_follows_the_offset(make_tab, config_file):
    tab = make_tab(config_file)
    tab.offset_spin.setValue(0)
    assert tab.offset_preview.text() == offset_preview(0.0)
    assert tab.save_button.isEnabled()


def test_offset_off_the_quarter_hour_is_marked(make_tab, config_file):
    tab = make_tab(config_file)
    tab.offset_spin.setValue(5.1)
    assert tab.offset_error.isVisibleTo(tab)
    assert tab.offset_error.text() == OFFSET_MESSAGE
    assert tab.offset_preview.text() == ""
    assert not tab.save_button.isEnabled()


def test_offset_stays_within_its_range(make_tab, config_file):
    tab = make_tab(config_file)
    tab.offset_spin.setValue(20)
    assert tab.offset_spin.value() == 14.0
    tab.offset_spin.setValue(-20)
    assert tab.offset_spin.value() == -12.0


# ---------------------------------------------------------------------------
# Coverage threshold (D39)
# ---------------------------------------------------------------------------


def test_coverage_threshold_shows_the_default(make_tab, config_file):
    tab = make_tab(config_file)
    assert tab.coverage_spin.value() == 99.0
    assert not tab.coverage_error.isVisibleTo(tab)


def test_coverage_threshold_shows_the_file(make_tab, config_file):
    write(config_file, "coverage_highlight_percent = 97.5\n")
    tab = make_tab(config_file)
    assert tab.coverage_spin.value() == 97.5
    assert not tab.save_button.isEnabled()


def test_coverage_threshold_change_enables_save_and_is_written(qtbot, make_tab, config_file):
    tab = make_tab(config_file)
    tab.coverage_spin.setValue(95.0)
    assert tab.save_button.isEnabled()
    config = save_and_get_config(qtbot, tab)
    assert config.coverage_highlight_percent == 95.0
    assert read_config_data(config_file)["coverage_highlight_percent"] == 95


def test_coverage_threshold_of_zero_is_marked(make_tab, config_file):
    tab = make_tab(config_file)
    tab.coverage_spin.setValue(0.0)
    assert tab.coverage_error.isVisibleTo(tab)
    assert tab.coverage_error.text() == COVERAGE_MESSAGE
    assert not tab.save_button.isEnabled()


def test_coverage_threshold_of_zero_in_the_file_is_marked(make_tab, config_file):
    write(config_file, "coverage_highlight_percent = 0\n")
    tab = make_tab(config_file)
    assert tab.coverage_error.isVisibleTo(tab)
    assert tab.problem_label.isVisibleTo(tab)
    tab.coverage_spin.setValue(99.0)
    assert tab.save_button.isEnabled()


def test_coverage_threshold_stays_at_most_100(make_tab, config_file):
    tab = make_tab(config_file)
    tab.coverage_spin.setValue(150.0)
    assert tab.coverage_spin.value() == 100.0


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


def test_save_writes_the_file_and_emits_the_config(qtbot, make_tab, config_file, db_path, replies):
    tab = make_tab(config_file)
    tab.db_edit.setText(str(db_path))
    replies.append((NAS + "\\", True))
    tab.add_root_button.click()
    tab.offset_spin.setValue(-3.5)
    config = save_and_get_config(qtbot, tab)
    assert config == Config(db_path=str(db_path), nas_roots=(NAS,), display_utc_offset_hours=-3.5)
    assert load_config(config_file) == config
    assert roots(tab) == [NAS]  # shown as written
    assert not tab.save_button.isEnabled()
    assert tab.message_label.text() == f"Saved {config_file}."
    assert tab.open_folder_button.isEnabled()  # the folder exists now


def test_save_keeps_other_keys_and_the_previous_file(qtbot, make_tab, config_file):
    original = (
        "# hand-written\nnetwork_speed_mb_s = 95\ncolour = 'blue'\n\n"
        f"[storage_roots]\n'{NAS}' = '/mnt/nas/recordings'\n"
    )
    write(config_file, original)
    tab = make_tab(config_file)
    tab.db_edit.setText(r"D:\catalog.db")
    save_and_get_config(qtbot, tab)
    data = read_config_data(config_file)
    assert data["network_speed_mb_s"] == 95
    assert data["colour"] == "blue"
    assert data["storage_roots"] == {NAS: "/mnt/nas/recordings"}
    assert data["db_path"] == r"D:\catalog.db"
    assert backup_path(config_file).read_text(encoding="utf-8") == original


def test_answering_no_writes_nothing(qtbot, make_tab, config_file):
    write(config_file, "db_path = 'old.db'\n")
    asked: list[Config] = []

    def confirm(config: Config) -> bool:
        asked.append(config)
        return False

    tab = make_tab(config_file, confirm_apply=confirm)
    tab.db_edit.setText("new.db")
    with qtbot.assertNotEmitted(tab.saved):
        tab.save_button.click()
    assert [c.db_path for c in asked] == ["new.db"]
    assert config_file.read_text(encoding="utf-8") == "db_path = 'old.db'\n"
    assert not backup_path(config_file).exists()
    assert tab.message_label.text() == "Not saved."
    assert tab.db_edit.text() == "new.db"  # the input stays


def test_a_failed_write_is_reported(make_tab, config_file, monkeypatch):
    tab = make_tab(config_file)
    tab.db_edit.setText("new.db")

    def fail(self, target):
        raise PermissionError("file in use")

    monkeypatch.setattr(Path, "replace", fail)
    tab.save_button.click()
    assert tab.message_label.text().startswith("Not saved:")
    assert "file in use" in tab.message_label.text()
    assert not config_file.exists()


def test_a_wrong_hidden_key_blocks_save(make_tab, config_file):
    write(config_file, "storage_roots = 5\n")
    tab = make_tab(config_file)
    tab.db_edit.setText("new.db")
    assert "storage_roots" in tab.problem_label.text()  # named, to fix by hand (D36)
    assert "Correct it in the file (Open folder)" in tab.problem_label.text()
    assert not tab.save_button.isEnabled()

    write(config_file, "network_speed_mb_s = 50\n")
    tab.reload_button.click()
    assert tab.problem_label.isHidden()
    assert tab.db_edit.text() == ""


# ---------------------------------------------------------------------------
# Transfers (Milestone 6; D34, D58)
# ---------------------------------------------------------------------------


def test_transfer_keys_are_shown_and_saved(qtbot, make_tab, config_file):
    write(
        config_file,
        "default_local_copy_root = 'D:\\work\\iq'\nnetwork_speed_mb_s = 95\n"
        "default_hash_mode = 'all'\nhash_sample_fraction = 0.1\nfree_space_margin_gb = 20\n"
        "copy_workers = 8\n",
    )
    tab = make_tab(config_file)
    assert tab.copy_root_edit.text() == r"D:\work\iq"
    assert tab.speed_spin.value() == 95.0
    assert tab.current_settings().default_hash_mode is HashMode.ALL
    assert tab.sample_spin.value() == 10.0
    assert tab.margin_spin.value() == 20.0
    assert tab.workers_spin.value() == 8
    assert not tab.save_button.isEnabled()  # nothing changed
    tab.workers_spin.setValue(2)
    tab.hash_mode_combo.setCurrentIndex(tab.hash_mode_combo.findData(HashMode.SAMPLE))
    tab.copy_root_edit.setText("")
    config = save_and_get_config(qtbot, tab)
    assert (config.copy_workers, config.default_hash_mode) == (2, HashMode.SAMPLE)
    assert config.default_local_copy_root is None
    assert config.network_speed_mb_s == 95.0
    assert "default_local_copy_root" not in read_config_data(config_file)


@pytest.mark.parametrize(
    ("field", "label", "message"),
    [
        ("speed_spin", "speed_error", "Use a speed above 0 MB/s."),
        ("sample_spin", "sample_error", "Use a share above 0 % and at most 100 %."),
    ],
)
def test_a_zero_speed_or_sample_is_marked_and_blocks_save(
    make_tab, config_file, field, label, message
):
    tab = make_tab(config_file)
    getattr(tab, field).setValue(0.0)
    assert getattr(tab, label).text() == message
    assert not getattr(tab, label).isHidden()
    assert not tab.save_button.isEnabled()


def test_a_sample_share_the_field_rounds_is_not_a_change(make_tab, config_file):
    write(config_file, "hash_sample_fraction = 0.0125\n")
    tab = make_tab(config_file)
    assert tab.sample_spin.value() == pytest.approx(1.3, abs=0.051)
    assert not tab.save_button.isEnabled()


def test_an_unreadable_file_can_be_replaced(qtbot, make_tab, config_file):
    write(config_file, "db_path = ")
    tab = make_tab(config_file)
    assert "The settings file cannot be read" in tab.problem_label.text()
    assert "not valid TOML" in tab.problem_label.toolTip()
    assert tab.save_button.isEnabled()  # without a change
    config = save_and_get_config(qtbot, tab)
    assert config == Config()
    assert load_config(config_file) == Config()
    assert backup_path(config_file).read_text(encoding="utf-8") == "db_path = "
    assert tab.problem_label.isHidden()


def test_reload_drops_changes(make_tab, config_file):
    write(config_file, "db_path = 'a.db'\n")
    tab = make_tab(config_file)
    tab.db_edit.setText("b.db")
    tab.offset_spin.setValue(0)
    tab.reload_button.click()
    assert (tab.db_edit.text(), tab.offset_spin.value()) == ("a.db", 8.0)
    assert not tab.save_button.isEnabled()


# ---------------------------------------------------------------------------
# Overrides and About
# ---------------------------------------------------------------------------


def test_db_override_is_named_and_save_writes_the_field(qtbot, make_tab, config_file):
    write(config_file, "db_path = 'file.db'\n")
    tab = make_tab(config_file, db_override="override.db")
    assert tab.db_edit.text() == "file.db"
    assert "override.db" in tab.db_override_note.text()
    assert tab.db_override_note.isVisibleTo(tab)
    assert "--db" in tab.override_note.text()
    tab.db_edit.setText("next.db")
    config = save_and_get_config(qtbot, tab)
    assert config.db_path == "next.db"
    assert load_config(config_file).db_path == "next.db"


def test_without_overrides_no_note(make_tab, config_file):
    tab = make_tab(config_file)
    assert not tab.db_override_note.isVisibleTo(tab)
    assert not tab.override_note.isVisibleTo(tab)


def test_config_override_is_named(make_tab, config_file):
    tab = make_tab(config_file, config_override=True)
    assert "--config" in tab.override_note.text()


def test_open_folder_opens_the_config_folder(make_tab, config_file):
    write(config_file, "")
    opened: list[Path] = []
    tab = make_tab(config_file, open_folder=opened.append)
    tab.open_folder_button.click()
    assert opened == [config_file.parent]


def test_version_is_shown(make_tab, config_file):
    from iqdm import __version__

    assert make_tab(config_file).version_label.text() == f"IQ Data Manager {__version__}"


# ---------------------------------------------------------------------------
# Light and dark themes
# ---------------------------------------------------------------------------


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


def test_error_marks_follow_the_theme(qapp, make_tab, config_file, replies, app_palette):
    app_palette(LIGHT)
    tab = make_tab(config_file)
    replies.append((r"D:\data", True))
    tab.add_root_button.click()
    light = LIGHT_COLOURS[ItemState.ERROR]
    assert tab.roots_list.item(0).foreground().color() == light
    assert light.name() in tab.roots_error.styleSheet()

    app_palette(DARK)
    qapp.processEvents()
    dark = DARK_COLOURS[ItemState.ERROR]
    assert tab.roots_list.item(0).foreground().color() == dark
    assert dark.name() in tab.roots_error.styleSheet()


@pytest.mark.parametrize(
    ("setup", "state"),
    [("current", ItemState.OK), ("newer", ItemState.INFO), ("absent", ItemState.ERROR)],
)
def test_database_status_is_green_amber_or_red_in_both_themes(
    qapp, qtbot, make_tab, config_file, db_path, app_palette, setup, state
):
    if setup == "newer":
        set_user_version(db_path, 3)
    path = db_path if setup != "absent" else db_path.parent / "absent.db"
    write(config_file, f"db_path = '{path}'")
    app_palette(LIGHT)
    tab = make_tab(config_file)
    assert tab.db_state.state is state
    assert LIGHT_COLOURS[state].name() in tab.db_status.styleSheet()
    app_palette(DARK)
    qapp.processEvents()
    assert DARK_COLOURS[state].name() in tab.db_status.styleSheet()
