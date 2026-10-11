"""Application entry point: the QApplication and the main window with four tabs."""

import argparse
import sys
from collections.abc import Mapping
from dataclasses import replace
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget, QWidget

from iqdm import __version__
from iqdm.config import (
    DEFAULTS_FILE_NAME,
    Config,
    ConfigError,
    default_config_path,
    load_config,
    settings_source,
)
from iqdm.db.connection import verify_schema_in_memory
from iqdm.db.version import LATEST_VERSION
from iqdm.gui.log_tab import LogTab
from iqdm.gui.settings_tab import SettingsTab
from iqdm.gui.transfer_tab import TransferTab
from iqdm.gui.viewer_tab import ViewerTab
from iqdm.transfer.manifest import manifests_dir

APP_NAME = "IQ Data Manager"
TAB_COUNT = 4
CLEAR_LOG_TAB_QUESTION = (
    "The new database file or NAS locations clear the Log tab form. The form holds input "
    "that is not saved.\n\nSave the settings and clear the form?"
)
LOG_TAB_SAVING = "The Log tab is saving a recording. Save the settings when it has finished."
LOG_TAB_SAVING_EDIT = (
    "The Log tab is saving a recording. Click Edit entry again when it has finished."
)
TRANSFER_RUNNING = (
    "An operation is running in the Archive / copy tab. Save the settings when it has "
    "finished."
)
TRANSFER_BUSY = (
    "An operation is running in the Archive / copy tab. Open the recording there when it "
    "has finished."
)
CLOSE_QUESTION = (
    "An operation is running in the Archive / copy tab.\n\nStop it and close the app? A "
    "stopped copy or archive can be resumed later."
)
TRANSFER_TAB = "Archive / copy"
SETTINGS_TAB = "Settings"
SETTINGS_UNSAVED_TAB = "Settings (not saved)"
UNSAVED_QUESTION = "The Settings tab has changes that are not saved.\n\nSave them now?"
UNSAVED_WRONG_VALUE = (
    "The Settings tab has changes that are not saved. A field holds a wrong value, so "
    "the changes cannot be saved.\n\nStay and correct the field, or drop the changes?"
)


class UnsavedChoice(StrEnum):
    """The answer to the question about unsaved settings (D70)."""

    SAVE = "save"
    DISCARD = "discard"
    STAY = "stay"


def ask_unsaved_settings(parent: QWidget, *, can_save: bool, closing: bool) -> UnsavedChoice:
    """Ask what to do with unsaved settings before leaving the tab or closing (D70)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Settings not saved")
    box.setText(UNSAVED_QUESTION if can_save else UNSAVED_WRONG_VALUE)
    buttons = {}
    if can_save:
        buttons[box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)] = UnsavedChoice.SAVE
    discard_text = "Close without saving" if closing else "Leave without saving"
    buttons[box.addButton(discard_text, QMessageBox.ButtonRole.DestructiveRole)] = (
        UnsavedChoice.DISCARD
    )
    stay = box.addButton("Stay", QMessageBox.ButtonRole.RejectRole)
    buttons[stay] = UnsavedChoice.STAY
    box.setDefaultButton(next(iter(buttons)) if can_save else stay)
    box.setEscapeButton(stay)
    box.exec()
    return buttons.get(box.clickedButton(), UnsavedChoice.STAY)


def drop_log_input_question(recording_id: int) -> str:
    return (
        "The Log tab form holds input that is not saved.\n\n"
        f"Open recording {recording_id} for editing and drop that input?"
    )


class MainWindow(QMainWindow):
    """Top-level window holding the Viewer, Log recording, Archive / copy and Settings tabs.

    config_path is the configuration file the Settings tab reads and writes. None means
    there is none (APPDATA not set). defaults_path is the defaults file the tab reads
    while config_path does not exist (D68). db_override is the --db path, which stays
    in force after a Save (SPEC section 4).
    """

    def __init__(
        self,
        config: Config | None = None,
        *,
        config_error: str | None = None,
        config_path: Path | None = None,
        defaults_path: Path | None = None,
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
        self.transfer_tab = TransferTab(
            self.config,
            manifests_dir=None if config_path is None else manifests_dir(config_path),
        )
        self.viewer_tab.transfer_requested.connect(self.open_transfer)
        self.log_tab.saved.connect(self.transfer_tab.recording_saved)
        self.transfer_tab.recording_changed.connect(lambda _id: self.viewer_tab.refresh())
        self.transfer_tab.pick_requested.connect(
            lambda: self.tabs.setCurrentWidget(self.viewer_tab)
        )
        self.transfer_tab.status_changed.connect(self._transfer_status)
        self.settings_tab = SettingsTab(
            config_path,
            defaults_path=defaults_path,
            db_override=db_override,
            config_override=config_override,
            confirm_apply=self.confirm_apply,
        )
        self.settings_tab.saved.connect(self.apply_config)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.viewer_tab, "Viewer")
        self.tabs.addTab(self.log_tab, "Log recording")
        self.tabs.addTab(self.transfer_tab, TRANSFER_TAB)
        self.tabs.addTab(self.settings_tab, SETTINGS_TAB)
        self.setCentralWidget(self.tabs)
        if config_error is not None:
            self.tabs.setCurrentWidget(self.settings_tab)  # correct the file there
        self.settings_tab.unsaved_changed.connect(self._settings_title)
        self._settings_title(self.settings_tab.has_changes())
        self._previous_tab = self.tabs.currentIndex()
        self.tabs.currentChanged.connect(self._tab_changed)

        self.statusBar().showMessage(status_text(self.config, config_error))

    def _settings_title(self, unsaved: bool) -> None:
        index = self.tabs.indexOf(self.settings_tab)
        self.tabs.setTabText(index, SETTINGS_UNSAVED_TAB if unsaved else SETTINGS_TAB)

    def _resolve_unsaved_settings(self, *, closing: bool) -> bool:
        """Ask about unsaved settings (D70). True when the user may leave the tab."""
        if not self.settings_tab.has_changes():
            return True
        choice = ask_unsaved_settings(
            self, can_save=self.settings_tab.can_save, closing=closing
        )
        if choice is UnsavedChoice.SAVE:
            return self.settings_tab.save()
        if choice is UnsavedChoice.DISCARD:
            if not closing:  # the window stays open, so the fields show the file again
                self.settings_tab.discard_changes()
            return True
        return False

    def _tab_changed(self, index: int) -> None:
        """Leaving the Settings tab with unsaved changes asks first (D70)."""
        settings = self.tabs.indexOf(self.settings_tab)
        previous, self._previous_tab = self._previous_tab, index
        if previous != settings or index == settings:
            return
        if not self._resolve_unsaved_settings(closing=False):
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(settings)
            self.tabs.blockSignals(False)
            self._previous_tab = settings

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
        if self.transfer_tab.is_busy:
            QMessageBox.information(self, "Settings not saved", TRANSFER_RUNNING)
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
        self.transfer_tab.apply_config(self.config)
        self.statusBar().showMessage(status_text(self.config, None))

    def open_transfer(self, recording_id: int) -> None:
        """Open a recording from the Viewer in the Archive / copy tab (D42)."""
        self.tabs.setCurrentWidget(self.transfer_tab)
        if self.transfer_tab.is_busy:
            QMessageBox.information(self, "Recording not opened", TRANSFER_BUSY)
            return
        self.transfer_tab.load_recording(recording_id)

    def _transfer_status(self, text: str) -> None:
        """Show a running operation in the tab's title and the status bar."""
        index = self.tabs.indexOf(self.transfer_tab)
        self.tabs.setTabText(index, f"{TRANSFER_TAB} ({text})" if text else TRANSFER_TAB)
        if text:
            self.statusBar().showMessage(f"{TRANSFER_TAB}: {text}")
        else:
            self.statusBar().showMessage(status_text(self.config, None))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  (Qt override)
        """Ask about unsaved settings (D70), then before closing while an operation runs.

        Yes to the second question stops the operation and waits for it.
        """
        if not self._resolve_unsaved_settings(closing=True):
            event.ignore()
            return
        if self.transfer_tab.is_busy:
            answer = QMessageBox.question(
                self,
                "Stop and close?",
                CLOSE_QUESTION,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.transfer_tab.stop(ask=False)
            self.transfer_tab.wait_until_idle()
        event.accept()

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


def defaults_path_for(frozen: bool | None = None, executable: str | None = None) -> Path | None:
    """defaults.toml in the folder of the packaged program; None when run from source (D68)."""
    if not (getattr(sys, "frozen", False) if frozen is None else frozen):
        return None
    return Path(sys.executable if executable is None else executable).parent / DEFAULTS_FILE_NAME


def resolve_config(
    args: argparse.Namespace,
    environ: Mapping[str, str] | None = None,
    defaults_path: Path | None = None,
) -> tuple[Config, str | None]:
    """The configuration for this run, and an error message if reading it failed.

    The settings file is read, or defaults_path while the settings file does not exist
    (D68). A failed read gives the defaults. --db overrides db_path in both cases
    (DECISIONS.md D15).
    """
    error = None
    try:
        path = args.config if args.config is not None else default_config_path(environ)
        config = load_config(settings_source(path, defaults_path))
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

    defaults_path = defaults_path_for()
    config, config_error = resolve_config(args, defaults_path=defaults_path)
    window = MainWindow(
        config,
        config_error=config_error,
        config_path=config_path_for(args),
        defaults_path=defaults_path,
        db_override=args.db,
        config_override=args.config is not None,
    )
    window.show()
    return app.exec()
