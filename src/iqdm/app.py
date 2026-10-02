"""Application entry point: the QApplication and the main window with four tabs."""

import argparse
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget, QWidget

from iqdm import __version__
from iqdm.config import Config, ConfigError, default_config_path, load_config
from iqdm.db.connection import verify_schema_in_memory
from iqdm.db.version import LATEST_VERSION
from iqdm.gui.log_tab import LogTab
from iqdm.gui.settings_tab import SettingsTab
from iqdm.gui.transfer_tab import TransferTab
from iqdm.gui.viewer_tab import ViewerTab

APP_NAME = "IQ Data Manager"
TAB_COUNT = 4
CLEAR_LOG_TAB_QUESTION = (
    "The new database path or NAS roots clear the Log tab form. The form holds input "
    "that is not saved.\n\nSave the settings and clear the form?"
)
LOG_TAB_SAVING = "The Log tab is saving a recording. Save the settings when it has finished."
LOG_TAB_SAVING_EDIT = (
    "The Log tab is saving a recording. Click Edit entry again when it has finished."
)


def drop_log_input_question(recording_id: int) -> str:
    return (
        "The Log tab form holds input that is not saved.\n\n"
        f"Open recording {recording_id} for editing and drop that input?"
    )


class MainWindow(QMainWindow):
    """Top-level window holding the Viewer, Log recording, Move / copy and Settings tabs.

    config_path is the configuration file the Settings tab reads and writes. None means
    there is none (APPDATA not set). db_override is the --db path, which stays in force
    after a Save (SPEC section 4).
    """

    def __init__(
        self,
        config: Config | None = None,
        *,
        config_error: str | None = None,
        config_path: Path | None = None,
        db_override: str | None = None,
        config_override: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = Config() if config is None else config
        self.db_override = db_override
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 800)

        self.viewer_tab = ViewerTab(self.config)
        self.log_tab = LogTab(self.config)
        self.viewer_tab.edit_requested.connect(self.edit_recording)
        self.log_tab.saved.connect(lambda _id: self.viewer_tab.refresh())
        self.transfer_tab = TransferTab()
        self.settings_tab = SettingsTab(
            config_path,
            db_override=db_override,
            config_override=config_override,
            confirm_apply=self.confirm_apply,
        )
        self.settings_tab.saved.connect(self.apply_config)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.viewer_tab, "Viewer")
        self.tabs.addTab(self.log_tab, "Log recording")
        self.tabs.addTab(self.transfer_tab, "Move / copy")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.setCentralWidget(self.tabs)
        if config_error is not None:
            self.tabs.setCurrentWidget(self.settings_tab)  # correct the file there

        self.statusBar().showMessage(status_text(self.config, config_error))

    def _effective(self, config: Config) -> Config:
        """`config` with the --db path in place of db_path, when --db is in force."""
        if self.db_override is None:
            return config
        return replace(config, db_path=self.db_override)

    def confirm_apply(self, new_config: Config) -> bool:
        """Asked by the Settings tab before it writes the file (O28). False cancels."""
        if self.log_tab.is_saving:
            QMessageBox.information(self, "Settings not saved", LOG_TAB_SAVING)
            return False
        effective = self._effective(new_config)
        if not self.log_tab.apply_clears_form(effective) or not self.log_tab.has_unsaved_input():
            return True
        answer = QMessageBox.question(
            self,
            "Clear the Log tab?",
            CLEAR_LOG_TAB_QUESTION,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def apply_config(self, config: Config) -> None:
        """Use a configuration the Settings tab saved, without a restart (O28)."""
        self.config = self._effective(config)
        self.log_tab.apply_config(self.config)
        self.viewer_tab.apply_config(self.config)
        self.statusBar().showMessage(status_text(self.config, None))

    def edit_recording(self, recording_id: int) -> None:
        """Open a recording from the Viewer in the Log tab's edit mode (D16, D45).

        Input in the Log tab form that is not saved is dropped only after a Yes.
        """
        if self.log_tab.is_saving:
            QMessageBox.information(self, "Recording not opened", LOG_TAB_SAVING_EDIT)
            return
        if self.log_tab.has_unsaved_input():
            answer = QMessageBox.question(
                self,
                "Drop the Log tab input?",
                drop_log_input_question(recording_id),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.tabs.setCurrentWidget(self.log_tab)
        self.log_tab.load_recording(recording_id)


def status_text(config: Config, config_error: str | None) -> str:
    """Status bar text: the configuration error, or which database is in use."""
    if config_error is not None:
        return f"Configuration error: {config_error}"
    if config.db_path is None:
        return "No database configured. Set the database path in the Settings tab."
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


def config_path_for(
    args: argparse.Namespace, environ: Mapping[str, str] | None = None
) -> Path | None:
    """The --config path, else config.toml in %APPDATA%. None when APPDATA is not set."""
    if args.config is not None:
        return args.config
    try:
        return default_config_path(environ)
    except ConfigError:
        return None


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
    if tab_count != TAB_COUNT:
        print(f"smoke test: expected {TAB_COUNT} tabs, found {tab_count}", file=sys.stderr)
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
    window = MainWindow(
        config,
        config_error=config_error,
        config_path=config_path_for(args),
        db_override=args.db,
        config_override=args.config is not None,
    )
    window.show()
    return app.exec()
