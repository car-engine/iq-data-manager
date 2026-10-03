"""Construction and wiring of the main window."""

import pytest
from PySide6.QtWidgets import QMessageBox

from iqdm import __version__
from iqdm.app import (
    CLOSE_QUESTION,
    LOG_TAB_SAVING,
    LOG_TAB_SAVING_EDIT,
    TRANSFER_BUSY,
    TRANSFER_RUNNING,
    MainWindow,
    _parse_args,
    config_path_for,
    drop_log_input_question,
    main,
    resolve_config,
    status_text,
)
from iqdm.config import Config, load_config
from iqdm.db import repository as repo
from iqdm.db.connection import schema_sql, write_transaction
from iqdm.models import Channel, Recording


@pytest.fixture
def smoke_app(qapp):
    """The shared QApplication, set so that main(["--smoke-test"]) leaves no quit behind.

    The smoke test runs the event loop and closes its window after the loop ends.
    With quitOnLastWindowClosed on, that close starts another quit. Later tests in
    the same process then received no queued signals from worker threads (seen with
    PySide6 6.11.2 and pytest-qt 4.5.0).
    """
    before = qapp.quitOnLastWindowClosed()
    qapp.setQuitOnLastWindowClosed(False)
    yield qapp
    qapp.setQuitOnLastWindowClosed(before)


def test_main_window_has_four_tabs_in_order(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert labels == ["Viewer", "Log recording", "Archive / copy", "Settings"]
    assert window.tabs.currentWidget() is window.viewer_tab


def test_window_title_shows_version(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == f"IQ Data Manager {__version__}"


def test_schema_resource_is_bundled():
    schema = schema_sql()
    assert "CREATE TABLE recordings" in schema
    assert "PRAGMA user_version" in schema


def test_smoke_test_flag_exits_zero(smoke_app):
    assert main(["--smoke-test"]) == 0


def test_smoke_test_exits_one_when_schema_missing(smoke_app, monkeypatch):
    def missing() -> str:
        raise FileNotFoundError("schema.sql")

    monkeypatch.setattr("iqdm.app.verify_schema_in_memory", missing)
    assert main(["--smoke-test"]) == 1


def test_smoke_test_exits_one_on_wrong_schema_version(smoke_app, monkeypatch):
    monkeypatch.setattr("iqdm.app.verify_schema_in_memory", lambda: 0)
    assert main(["--smoke-test"]) == 1


# ---------------------------------------------------------------------------
# Configuration flags (DECISIONS.md D15)
# ---------------------------------------------------------------------------


def test_config_flag_reads_the_given_file(tmp_path):
    path = tmp_path / "my.toml"
    path.write_text("db_path = 'from-file.db'\nnetwork_speed_mb_s = 50", encoding="utf-8")
    config, error = resolve_config(_parse_args(["--config", str(path)]))
    assert error is None
    assert config.db_path == "from-file.db"
    assert config.network_speed_mb_s == 50.0


def test_db_flag_overrides_db_path(tmp_path):
    path = tmp_path / "my.toml"
    path.write_text("db_path = 'from-file.db'", encoding="utf-8")
    args = _parse_args(["--config", str(path), "--db", "other.db"])
    config, error = resolve_config(args)
    assert (config.db_path, error) == ("other.db", None)


def test_default_config_path_comes_from_appdata(tmp_path):
    folder = tmp_path / "IQDataManager"
    folder.mkdir()
    (folder / "config.toml").write_text("db_path = 'appdata.db'", encoding="utf-8")
    config, error = resolve_config(_parse_args([]), {"APPDATA": str(tmp_path)})
    assert (config.db_path, error) == ("appdata.db", None)


def test_bad_config_gives_defaults_and_an_error(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("db_path = ", encoding="utf-8")
    config, error = resolve_config(_parse_args(["--config", str(path), "--db", "x.db"]))
    assert config == Config(db_path="x.db")
    assert error is not None
    assert "not valid TOML" in error


def test_status_bar_names_the_database(qtbot, db_path):
    window = MainWindow(Config(db_path=str(db_path)))
    qtbot.addWidget(window)
    assert window.statusBar().currentMessage() == f"Database: {db_path}"
    assert window.log_tab.config.db_path == str(db_path)
    qtbot.waitUntil(lambda: not window.log_tab.runner.busy, timeout=10_000)


def test_status_text_without_database_or_with_an_error():
    assert "No database configured" in status_text(Config(), None)
    assert status_text(Config(), "boom") == "Configuration error: boom"


# ---------------------------------------------------------------------------
# Settings tab in the main window (Milestone 3a)
# ---------------------------------------------------------------------------


def test_config_path_for(tmp_path):
    given = tmp_path / "my.toml"
    assert config_path_for(_parse_args(["--config", str(given)]), {}) == given
    assert config_path_for(_parse_args([]), {"APPDATA": str(tmp_path)}) == (
        tmp_path / "IQDataManager" / "config.toml"
    )
    assert config_path_for(_parse_args([]), {}) is None


def make_window(qtbot, config_file, **kw) -> MainWindow:
    config, error = resolve_config(_parse_args(["--config", str(config_file)]))
    window = MainWindow(config, config_error=error, config_path=config_file, **kw)
    qtbot.addWidget(window)
    wait_window(qtbot, window)
    return window


def wait_window(qtbot, window: MainWindow) -> None:
    for runner in (
        window.viewer_tab.runner,
        window.log_tab.runner,
        window.settings_tab.runner,
        window.transfer_tab.runner,
    ):
        qtbot.waitUntil(lambda r=runner: not r.busy, timeout=10_000)


def save_settings(qtbot, window: MainWindow) -> None:
    window.settings_tab.save_button.click()
    wait_window(qtbot, window)


@pytest.fixture
def questions(monkeypatch) -> list[str]:
    """Record QMessageBox.question calls and answer No. A real box would block."""
    asked: list[str] = []

    def question(parent, title, text, *args):
        asked.append(text)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", question)
    return asked


def test_bad_config_opens_on_the_settings_tab(qtbot, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("db_path = ", encoding="utf-8")
    window = make_window(qtbot, path)
    assert window.tabs.currentWidget() is window.settings_tab
    assert window.statusBar().currentMessage().startswith("Configuration error:")
    assert "cannot be read" in window.settings_tab.problem_label.text()


def test_good_config_opens_on_the_viewer(qtbot, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    window = make_window(qtbot, path)
    assert window.tabs.currentWidget() is window.viewer_tab


def test_saved_settings_apply_without_a_restart(qtbot, tmp_path, db_path):
    path = tmp_path / "config.toml"
    window = make_window(qtbot, path)
    assert window.log_tab.config.db_path is None
    window.settings_tab.db_edit.setText(str(db_path))
    window.settings_tab.offset_spin.setValue(0)
    save_settings(qtbot, window)
    assert window.statusBar().currentMessage() == f"Database: {db_path}"
    assert window.config == Config(db_path=str(db_path), display_utc_offset_hours=0.0)
    assert window.log_tab.config == window.config
    assert window.log_tab.start_label.text().startswith("Start (UTC)")


def test_db_override_stays_in_force_after_save(qtbot, tmp_path, db_path):
    path = tmp_path / "config.toml"
    window = make_window(qtbot, path, db_override=str(db_path))
    window.settings_tab.db_edit.setText("written-to-file.db")
    save_settings(qtbot, window)
    assert load_config(path).db_path == "written-to-file.db"
    assert window.config.db_path == str(db_path)
    assert window.log_tab.config.db_path == str(db_path)


def test_unsaved_log_input_answer_no_keeps_everything(qtbot, tmp_path, db_path, questions):
    path = tmp_path / "config.toml"
    path.write_text(f"db_path = '{db_path}'\n", encoding="utf-8")
    window = make_window(qtbot, path)
    window.log_tab.remarks_edit.setPlainText("not saved yet")
    window.settings_tab.db_edit.setText(str(tmp_path / "other.db"))
    save_settings(qtbot, window)
    assert len(questions) == 1
    assert "clear the Log tab form" in questions[0]
    assert path.read_text(encoding="utf-8") == f"db_path = '{db_path}'\n"
    assert window.log_tab.remarks_edit.toPlainText() == "not saved yet"
    assert window.config.db_path == str(db_path)


def test_unsaved_log_input_answer_yes_clears_the_form(qtbot, tmp_path, db_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    path = tmp_path / "config.toml"
    path.write_text(f"db_path = '{db_path}'\n", encoding="utf-8")
    window = make_window(qtbot, path)
    window.log_tab.remarks_edit.setPlainText("not saved yet")
    window.settings_tab.offset_spin.setValue(1)
    window.settings_tab.db_edit.setText("")
    save_settings(qtbot, window)
    assert load_config(path).db_path is None
    assert window.log_tab.remarks_edit.toPlainText() == ""
    assert window.statusBar().currentMessage().startswith("No database configured")


def test_offset_change_asks_nothing_and_keeps_the_form(qtbot, tmp_path, db_path, questions):
    path = tmp_path / "config.toml"
    path.write_text(f"db_path = '{db_path}'\n", encoding="utf-8")
    window = make_window(qtbot, path)
    window.log_tab.remarks_edit.setPlainText("not saved yet")
    window.settings_tab.offset_spin.setValue(1)
    save_settings(qtbot, window)
    assert questions == []
    assert load_config(path).display_utc_offset_hours == 1.0
    assert window.log_tab.remarks_edit.toPlainText() == "not saved yet"


def test_settings_wait_for_a_log_tab_save(qtbot, tmp_path, db_path, monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda parent, title, text, *a: shown.append(text)
    )
    path = tmp_path / "config.toml"
    window = make_window(qtbot, path)
    window.log_tab._saving = True
    window.settings_tab.db_edit.setText(str(db_path))
    save_settings(qtbot, window)
    window.log_tab._saving = False
    assert shown == [LOG_TAB_SAVING]
    assert not path.exists()


# ---------------------------------------------------------------------------
# Viewer in the main window (Milestone 4)
# ---------------------------------------------------------------------------

T0 = 1790733600.0


def add_recording(db_path, rel_path: str, start: float = T0) -> int:
    def fill(conn):
        site = repo.find_site(conn, "SiteA") or repo.add_site(conn, "SiteA")
        ch = Channel(
            channel_index=0, fc_hz=145.8e6, fs_hz=1e3, start_unix=start, end_unix=start + 10
        )
        return repo.insert_recording(
            conn,
            Recording(
                logged_by="userA",
                site_id=site.id,
                storage_root="C:/x",
                rel_path=rel_path,
                channels=[ch],
            ),
        )

    return write_transaction(db_path, fill)


def window_with_recording(qtbot, tmp_path, db_path) -> tuple[MainWindow, int]:
    rid = add_recording(db_path, "rec1")
    path = tmp_path / "config.toml"
    path.write_text(f"db_path = '{db_path}'\n", encoding="utf-8")
    window = make_window(qtbot, path)
    assert window.viewer_tab.select_recording(rid)
    wait_window(qtbot, window)
    return window, rid


def test_viewer_gets_the_configuration(qtbot, tmp_path, db_path):
    window, rid = window_with_recording(qtbot, tmp_path, db_path)
    assert window.viewer_tab.config == window.config
    assert window.viewer_tab.selected_id == rid


def test_edit_entry_opens_the_log_tab_in_edit_mode(qtbot, tmp_path, db_path, questions):
    window, rid = window_with_recording(qtbot, tmp_path, db_path)
    window.viewer_tab.edit_button.click()
    wait_window(qtbot, window)
    assert questions == []
    assert window.tabs.currentWidget() is window.log_tab
    assert window.log_tab.editing is not None
    assert window.log_tab.editing.id == rid


def test_edit_entry_answer_no_keeps_the_log_input(qtbot, tmp_path, db_path, questions):
    window, rid = window_with_recording(qtbot, tmp_path, db_path)
    window.log_tab.remarks_edit.setPlainText("not saved yet")
    window.viewer_tab.edit_button.click()
    wait_window(qtbot, window)
    assert questions == [drop_log_input_question(rid)]
    assert window.tabs.currentWidget() is window.viewer_tab
    assert window.log_tab.editing is None
    assert window.log_tab.remarks_edit.toPlainText() == "not saved yet"


def test_edit_entry_answer_yes_drops_the_log_input(qtbot, tmp_path, db_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window, rid = window_with_recording(qtbot, tmp_path, db_path)
    window.log_tab.remarks_edit.setPlainText("not saved yet")
    window.viewer_tab.edit_button.click()
    wait_window(qtbot, window)
    assert window.log_tab.editing is not None
    assert window.log_tab.editing.id == rid
    assert window.log_tab.remarks_edit.toPlainText() == ""


def test_edit_entry_waits_for_a_log_tab_save(qtbot, tmp_path, db_path, monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda parent, title, text, *a: shown.append(text)
    )
    window, _rid = window_with_recording(qtbot, tmp_path, db_path)
    window.log_tab._saving = True
    window.viewer_tab.edit_button.click()
    window.log_tab._saving = False
    assert shown == [LOG_TAB_SAVING_EDIT]
    assert window.tabs.currentWidget() is window.viewer_tab


class _RunningTask:
    """Stands in for a running operation in the Archive / copy tab."""

    def cancel(self) -> None:
        pass


def test_archive_copy_opens_the_recording_in_its_tab(qtbot, tmp_path, db_path):
    window, rid = window_with_recording(qtbot, tmp_path, db_path)
    window.viewer_tab.transfer_button.click()
    wait_window(qtbot, window)
    assert window.tabs.currentWidget() is window.transfer_tab
    assert window.transfer_tab.recording is not None
    assert window.transfer_tab.recording.id == rid
    assert window.transfer_tab.manifests_dir == tmp_path / "manifests"


def test_archive_copy_waits_for_a_running_operation(qtbot, tmp_path, db_path, monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda parent, title, text, *a: shown.append(text)
    )
    window, _rid = window_with_recording(qtbot, tmp_path, db_path)
    window.transfer_tab._task = _RunningTask()
    window.viewer_tab.transfer_button.click()
    window.transfer_tab._task = None
    assert shown == [TRANSFER_BUSY]
    assert window.transfer_tab.recording is None


def test_settings_wait_for_a_running_operation(qtbot, tmp_path, db_path, monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda parent, title, text, *a: shown.append(text)
    )
    window, _rid = window_with_recording(qtbot, tmp_path, db_path)
    window.transfer_tab._task = _RunningTask()
    assert not window.confirm_apply(window.config)
    window.transfer_tab._task = None
    assert shown == [TRANSFER_RUNNING]


def test_the_tab_title_shows_a_running_operation(qtbot, tmp_path, db_path):
    window, _rid = window_with_recording(qtbot, tmp_path, db_path)
    index = window.tabs.indexOf(window.transfer_tab)
    window.transfer_tab.status_changed.emit("copying 41 %")
    assert window.tabs.tabText(index) == "Archive / copy (copying 41 %)"
    assert window.statusBar().currentMessage() == "Archive / copy: copying 41 %"
    window.transfer_tab.status_changed.emit("")
    assert window.tabs.tabText(index) == "Archive / copy"


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
def test_closing_during_an_operation_asks_first(qtbot, tmp_path, db_path, monkeypatch, answer):
    asked: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda parent, title, text, *a: asked.append(text) or answer
    )
    window, _rid = window_with_recording(qtbot, tmp_path, db_path)
    calls: list[str] = []
    monkeypatch.setattr(window.transfer_tab, "stop", lambda ask=True: calls.append(f"stop {ask}"))
    monkeypatch.setattr(window.transfer_tab, "wait_until_idle", lambda: calls.append("wait"))
    window.transfer_tab._task = _RunningTask()
    closed = window.close()
    window.transfer_tab._task = None
    assert asked == [CLOSE_QUESTION]
    if answer == QMessageBox.StandardButton.No:
        assert not closed
        assert calls == []
    else:
        assert closed
        assert calls == ["stop False", "wait"]


def test_closing_when_idle_asks_nothing(qtbot, tmp_path, db_path, questions):
    window, _rid = window_with_recording(qtbot, tmp_path, db_path)
    assert window.close()
    assert questions == []


def test_a_log_tab_save_refreshes_the_viewer(qtbot, tmp_path, db_path):
    window, rid = window_with_recording(qtbot, tmp_path, db_path)
    new_id = add_recording(db_path, "rec2", start=T0 + 100)
    window.log_tab.saved.emit(new_id)
    wait_window(qtbot, window)
    model = window.viewer_tab.model
    assert {model.summary(r).id for r in range(model.rowCount())} == {rid, new_id}
    assert window.viewer_tab.selected_id == rid


def test_saved_settings_reach_the_viewer(qtbot, tmp_path, db_path):
    window, _rid = window_with_recording(qtbot, tmp_path, db_path)
    window.settings_tab.coverage_spin.setValue(90.0)
    window.settings_tab.offset_spin.setValue(0)
    save_settings(qtbot, window)
    assert window.viewer_tab.config.coverage_highlight_percent == 90.0
    assert window.viewer_tab.start_from_label.text() == "Start date from (UTC)"
