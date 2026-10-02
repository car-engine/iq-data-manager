"""Construction and wiring of the main window."""

from iqdm import __version__
from iqdm.app import MainWindow, _parse_args, main, resolve_config, status_text
from iqdm.config import Config
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


def test_status_bar_names_the_database(qtbot):
    window = MainWindow(Config(db_path="dev/m3.db"))
    qtbot.addWidget(window)
    assert window.statusBar().currentMessage() == "Database: dev/m3.db"


def test_status_text_without_database_or_with_an_error():
    assert "No database configured" in status_text(Config(), None)
    assert status_text(Config(), "boom") == "Configuration error: boom"
