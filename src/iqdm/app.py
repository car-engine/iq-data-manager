"""Application entry point: the QApplication and the main window with three tabs."""

import argparse
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

from iqdm import __version__
from iqdm.config import Config, ConfigError, default_config_path, load_config
from iqdm.db.connection import verify_schema_in_memory
from iqdm.db.version import LATEST_VERSION
from iqdm.gui.log_tab import LogTab
from iqdm.gui.transfer_tab import TransferTab
from iqdm.gui.viewer_tab import ViewerTab

APP_NAME = "IQ Data Manager"


class MainWindow(QMainWindow):
    """Top-level window holding the Viewer, Log recording and Move / copy tabs."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        config_error: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = Config() if config is None else config
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 800)

        self.viewer_tab = ViewerTab()
        self.log_tab = LogTab(self.config)
        self.transfer_tab = TransferTab()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.viewer_tab, "Viewer")
        self.tabs.addTab(self.log_tab, "Log recording")
        self.tabs.addTab(self.transfer_tab, "Move / copy")
        self.setCentralWidget(self.tabs)

        self.statusBar().showMessage(status_text(self.config, config_error))


def status_text(config: Config, config_error: str | None) -> str:
    """Status bar text: the configuration error, or which database is in use."""
    if config_error is not None:
        return f"Configuration error: {config_error}"
    if config.db_path is None:
        return "No database configured. Set db_path in the configuration file."
    return f"Database: {config.db_path}"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="iqdm", description=APP_NAME)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="build the main window, quit at once and exit with 0 on success",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="read this configuration file instead of config.toml in %%APPDATA%%",
    )
    parser.add_argument(
        "--db", metavar="PATH", help="use this database file instead of db_path in the config"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def resolve_config(
    args: argparse.Namespace, environ: Mapping[str, str] | None = None
) -> tuple[Config, str | None]:
    """The configuration for this run, and an error message if reading it failed.

    A failed read gives the defaults. --db overrides db_path in both cases
    (DECISIONS.md D15).
    """
    error = None
    try:
        path = args.config if args.config is not None else default_config_path(environ)
        config = load_config(path)
    except ConfigError as exc:
        config, error = Config(), str(exc)
    if args.db is not None:
        config = replace(config, db_path=args.db)
    return config, error


def _smoke_test(app: QApplication) -> int:
    """Check the bundled schema and the main window, then quit. Returns an exit code.

    The schema is built in an in-memory database, which also exercises the bundled
    sqlite3 module. A windowed PyInstaller build has no console, so the exit code is
    the result.
    """
    try:
        built_version = verify_schema_in_memory()
        if built_version != LATEST_VERSION:
            print(
                f"smoke test: schema built version {built_version}, expected {LATEST_VERSION}",
                file=sys.stderr,
            )
            return 1
        window = MainWindow()
        window.show()
        QTimer.singleShot(0, app.quit)
        app.exec()
        tab_count = window.tabs.count()
        window.close()
    except Exception as exc:
        print(f"smoke test failed: {exc!r}", file=sys.stderr)
        return 1
    if tab_count != 3:
        print(f"smoke test: expected 3 tabs, found {tab_count}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Start the GUI. Returns the process exit code."""
    args = _parse_args(argv)
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)

    if args.smoke_test:
        return _smoke_test(app)

    config, config_error = resolve_config(args)
    window = MainWindow(config, config_error=config_error)
    window.show()
    return app.exec()
