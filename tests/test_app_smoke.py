"""Construction and wiring of the main window."""

from iqdm import __version__
from iqdm.app import MainWindow, main
from iqdm.db.connection import schema_sql


def test_main_window_has_three_tabs_in_order(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert labels == ["Viewer", "Log recording", "Move / copy"]


def test_window_title_shows_version(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == f"IQ Data Manager {__version__}"


def test_schema_resource_is_bundled():
    schema = schema_sql()
    assert "CREATE TABLE recordings" in schema
    assert "PRAGMA user_version" in schema


def test_smoke_test_flag_exits_zero(qapp):
    assert main(["--smoke-test"]) == 0


def test_smoke_test_exits_one_when_schema_missing(qapp, monkeypatch):
    def missing() -> str:
        raise FileNotFoundError("schema.sql")

    monkeypatch.setattr("iqdm.app.verify_schema_in_memory", missing)
    assert main(["--smoke-test"]) == 1


def test_smoke_test_exits_one_on_wrong_schema_version(qapp, monkeypatch):
    monkeypatch.setattr("iqdm.app.verify_schema_in_memory", lambda: 0)
    assert main(["--smoke-test"]) == 1
