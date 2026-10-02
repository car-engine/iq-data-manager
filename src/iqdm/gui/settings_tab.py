"""Settings tab: edit config.toml and show the state of the database.

SPEC section 4, "Settings tab" (DECISIONS.md D29, D30). The file is read and written
through iqdm.config, which has no Qt. Database checks run in a TaskRunner, because a
database on the NAS can take seconds to answer. The tab never creates or changes a
database: inspect_database() opens the file read-only.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from iqdm import __version__
from iqdm.config import (
    OFFSET_MAX_HOURS,
    OFFSET_MIN_HOURS,
    OFFSET_STEP_HOURS,
    Config,
    ConfigError,
    SettingsInput,
    hidden_key_error,
    merge_settings,
    nas_root_error,
    parse_config,
    read_config_data,
    save_config,
    settings_errors,
    settings_from_data,
)
from iqdm.db.connection import DatabaseInfo, inspect_database
from iqdm.db.version import SchemaStatus
from iqdm.entry import ItemState
from iqdm.gui.widgets.checklist import colours_for
from iqdm.gui.workers import TaskRunner
from iqdm.timeutil import display_time, iso_to_unix, offset_label

PREVIEW_ISO = "2026-09-30T02:00:00Z"  # a fixed instant for the offset preview
NO_DB_PATH = "No database path. The Log tab cannot save until one is set."
DB_FILE_FILTER = "SQLite database (*.db);;All files (*)"
FILE_NOTE = (
    "Save rewrites the configuration file. Keys that this tab does not show stay in "
    "the file. Comments in the file are lost. The previous file is kept as "
    "config.toml.bak."
)
ROOTS_RULE = (
    "A folder under a NAS root is logged as archived, with a log entry that marks it "
    "as not verified (DECISIONS.md D14, D2). Each root is a UNC path, for example "
    "\\\\server\\share."
)
NO_CONFIG_PATH = (
    "The app has no configuration file, because the APPDATA environment variable is "
    "not set. Start the app with --config PATH."
)


def database_status_text(info: DatabaseInfo) -> str:
    """The status line for a database file (SPEC section 4; D6, D30)."""
    if info.error is not None:
        return info.error
    found, latest = info.user_version, info.latest_version
    match info.status:
        case SchemaStatus.CURRENT:
            state = f"Schema version {found}, current."
        case SchemaStatus.NEEDS_UPGRADE:
            state = (
                f"Schema version {found}, needs an upgrade to version {latest}. "
                "This version of the app cannot read or write this database."
            )
        case SchemaStatus.TOO_NEW:
            state = (
                f"Schema version {found}, too new: this app expects version {latest}. "
                "The app can read this database but cannot write to it."
            )
        case _:
            state = f"Not an IQ Data Manager database (schema version {found})."
    settings = info.settings or {}
    keys = "on" if settings.get("foreign_keys") else "off"
    pragmas = (
        f"Journal mode {settings.get('journal_mode')}, foreign keys {keys}, "
        f"busy timeout {settings.get('busy_timeout')} ms."
    )
    return f"File found. {state} {pragmas}"


def offset_preview(hours: float) -> str:
    """'2026-09-30T02:00:00Z is shown as 2026-09-30 10:00:00 (UTC+8).'"""
    shown = display_time(iso_to_unix(PREVIEW_ISO), hours)
    return f"{PREVIEW_ISO} is shown as {shown} ({offset_label(hours)})."


def _open_in_explorer(folder: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


class SettingsTab(QWidget):
    """Form for config.toml, with the state of the configured database."""

    saved = Signal(object)  # the Config now in the file, without --db

    def __init__(
        self,
        config_path: Path | None,
        *,
        db_override: str | None = None,
        config_override: bool = False,
        confirm_apply: Callable[[Config], bool] | None = None,
        open_folder: Callable[[Path], None] = _open_in_explorer,
        runner: TaskRunner | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_path = config_path
        self.db_override = db_override
        self.config_override = config_override
        self.confirm_apply = confirm_apply  # asked before Save writes; False cancels
        self._open_folder = open_folder
        self.runner = TaskRunner(self) if runner is None else runner

        self._data: dict[str, Any] | None = {}  # None when the file cannot be read
        self._baseline = SettingsInput()
        self._read_error: str | None = None  # the file is not valid TOML
        self._file_error: str | None = None  # valid TOML that load_config() refuses
        self._hidden_error: str | None = None  # a wrong key that the tab does not show
        self._check_id = 0
        self._checked_path: str | None = None

        self._build()
        self.reload()

    # =====================================================================
    # Layout
    # =====================================================================

    def _build(self) -> None:
        column = QVBoxLayout()
        column.addWidget(self._build_database())
        column.addWidget(self._build_nas_roots())
        column.addWidget(self._build_display())
        column.addWidget(self._build_about())
        column.addStretch(1)
        inner = QWidget()
        inner.setLayout(column)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        self.file_note = QLabel(FILE_NOTE)
        self.file_note.setWordWrap(True)
        self.problem_label = QLabel()
        self.problem_label.setWordWrap(True)
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save)
        self.reload_button = QPushButton("Reload from file")
        self.reload_button.setToolTip("Read the file again and drop changes that are not saved.")
        self.reload_button.clicked.connect(self._reload_clicked)
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.reload_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.problem_label)
        layout.addWidget(self.file_note)
        layout.addLayout(buttons)
        layout.addWidget(self.message_label)

    def _build_database(self) -> QGroupBox:
        box = QGroupBox("Database")
        self.db_edit = QLineEdit()
        self.db_edit.setPlaceholderText("Path of the catalogue database (.db)")
        self.db_edit.textChanged.connect(self._validate)
        self.db_edit.editingFinished.connect(self._db_edit_finished)
        self.db_browse_button = QPushButton("Browse...")
        self.db_browse_button.clicked.connect(self._browse_db)
        self.check_button = QPushButton("Check connection")
        self.check_button.clicked.connect(self.check_database)
        self.db_status = QLabel()
        self.db_status.setWordWrap(True)
        self.db_override_note = QLabel()
        self.db_override_note.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(self.db_edit, 1)
        row.addWidget(self.db_browse_button)
        row.addWidget(self.check_button)
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("Database file (db_path)"))
        layout.addLayout(row)
        layout.addWidget(self.db_status)
        layout.addWidget(self.db_override_note)
        return box

    def _build_nas_roots(self) -> QGroupBox:
        box = QGroupBox("NAS roots")
        self.roots_list = QListWidget()
        self.roots_list.setMaximumHeight(120)
        self.roots_list.currentRowChanged.connect(self._update_root_buttons)
        self.roots_list.itemDoubleClicked.connect(lambda _item: self.edit_root())
        self.add_root_button = QPushButton("Add...")
        self.add_root_button.clicked.connect(self.add_root)
        self.edit_root_button = QPushButton("Edit...")
        self.edit_root_button.clicked.connect(self.edit_root)
        self.remove_root_button = QPushButton("Remove")
        self.remove_root_button.clicked.connect(self.remove_root)
        self.roots_error = QLabel()
        self.roots_error.setWordWrap(True)
        rule = QLabel(ROOTS_RULE)
        rule.setWordWrap(True)

        buttons = QVBoxLayout()
        buttons.addWidget(self.add_root_button)
        buttons.addWidget(self.edit_root_button)
        buttons.addWidget(self.remove_root_button)
        buttons.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.roots_list, 1)
        row.addLayout(buttons)
        layout = QVBoxLayout(box)
        layout.addWidget(rule)
        layout.addLayout(row)
        layout.addWidget(self.roots_error)
        return box

    def _build_display(self) -> QGroupBox:
        box = QGroupBox("Display")
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(OFFSET_MIN_HOURS, OFFSET_MAX_HOURS)
        self.offset_spin.setSingleStep(OFFSET_STEP_HOURS)
        self.offset_spin.setDecimals(2)
        self.offset_spin.setSuffix(" h")
        self.offset_spin.valueChanged.connect(self._validate)
        self.offset_preview = QLabel()
        self.offset_error = QLabel()
        self.offset_error.setWordWrap(True)
        note = QLabel(
            "Displayed times only. The database stores UTC (DECISIONS.md D24). "
            "Allowed values: -12 to 14 hours in steps of 0.25."
        )
        note.setWordWrap(True)

        layout = QFormLayout(box)
        layout.addRow("Offset from UTC (display_utc_offset_hours)", self.offset_spin)
        layout.addRow("Preview", self.offset_preview)
        layout.addRow(self.offset_error)
        layout.addRow(note)
        return box

    def _build_about(self) -> QGroupBox:
        box = QGroupBox("About")
        self.config_path_label = QLabel()
        self.config_path_label.setWordWrap(True)
        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.clicked.connect(self.open_config_folder)
        self.version_label = QLabel(f"IQ Data Manager {__version__}")
        self.override_note = QLabel()
        self.override_note.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(self.config_path_label, 1)
        row.addWidget(self.open_folder_button)
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("Configuration file"))
        layout.addLayout(row)
        layout.addWidget(self.override_note)
        layout.addWidget(self.version_label)
        return box

    # =====================================================================
    # State
    # =====================================================================

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802  (Qt override)
        """Follow a switch between the light and dark theme."""
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        ):
            self._validate()
        super().changeEvent(event)

    def show_message(self, text: str) -> None:
        self.message_label.setText(text)

    def current_settings(self) -> SettingsInput:
        return SettingsInput(
            db_path=self.db_edit.text().strip(),
            nas_roots=tuple(self.roots_list.item(i).text() for i in range(self.roots_list.count())),
            display_utc_offset_hours=self.offset_spin.value(),
        )

    def has_changes(self) -> bool:
        """True when the fields differ from the file as last read."""
        return self.current_settings() != self._baseline

    def reload(self) -> None:
        """Read the configuration file again and show its values."""
        self._data, self._read_error, self._file_error, self._hidden_error = {}, None, None, None
        if self.config_path is not None:
            where = str(self.config_path)
            try:
                self._data = read_config_data(self.config_path)
            except ConfigError as exc:
                self._data = None
                self._read_error = str(exc)
            else:
                try:
                    parse_config(self._data, where)
                except ConfigError as exc:
                    self._file_error = str(exc)
                self._hidden_error = hidden_key_error(self._data, where)
        self._baseline = settings_from_data(self._data or {})
        self._show_settings(self._baseline)
        self._show_about()
        self.check_database()

    def _reload_clicked(self) -> None:
        self.reload()
        self.show_message("Read the file again.")

    def _show_settings(self, settings: SettingsInput) -> None:
        self.db_edit.setText(settings.db_path)
        self.roots_list.clear()
        for root in settings.nas_roots:
            self.roots_list.addItem(QListWidgetItem(root))
        self.offset_spin.setValue(settings.display_utc_offset_hours)
        self._update_root_buttons()
        self._validate()

    def _show_about(self) -> None:
        path = self.config_path
        self.config_path_label.setText(str(path) if path is not None else "None")
        self.open_folder_button.setEnabled(path is not None and path.parent.is_dir())
        notes = []
        if self.config_override:
            notes.append("Started with --config: this run reads and writes the file above.")
        if self.db_override is not None:
            notes.append(f"Started with --db: this run uses {self.db_override}.")
        self.override_note.setText(" ".join(notes))
        self.override_note.setVisible(bool(notes))
        if self.db_override is not None:
            self.db_override_note.setText(
                f"Started with --db: this run uses {self.db_override}. Save writes the "
                "path above to the file. The --db path stays in force until the app "
                "restarts."
            )
        self.db_override_note.setVisible(self.db_override is not None)

    def _problem_text(self) -> str:
        if self.config_path is None:
            return NO_CONFIG_PATH
        if self._read_error is not None:
            return (
                f"The file cannot be read: {self._read_error}. Save replaces it with the "
                "values shown here. The old file is kept as config.toml.bak."
            )
        if self._hidden_error is not None:
            return (
                f"{self._hidden_error}. This tab does not show that key. Correct it in "
                "the file by hand, then click Reload from file."
            )
        if self._file_error is not None:
            return f"{self._file_error}. Correct the value here and save."
        return ""

    def _validate(self, *_: object) -> None:
        """Mark wrong fields, update the preview and enable Save when it can run."""
        settings = self.current_settings()
        errors = settings_errors(settings)
        error_colour = colours_for(self.palette())[ItemState.ERROR]
        error_style = f"color: {error_colour.name()};"
        text_brush = self.roots_list.palette().text()
        for i in range(self.roots_list.count()):
            item = self.roots_list.item(i)
            problem = nas_root_error(item.text().strip())
            if problem is None:
                item.setForeground(text_brush)
            else:
                item.setForeground(error_colour)
            item.setToolTip(problem or "")
        self.roots_error.setText(errors.get("nas_roots", ""))
        self.roots_error.setStyleSheet(error_style)
        self.roots_error.setVisible("nas_roots" in errors)

        offset_problem = errors.get("display_utc_offset_hours")
        self.offset_error.setText(offset_problem or "")
        self.offset_error.setStyleSheet(error_style)
        self.offset_error.setVisible(offset_problem is not None)
        hours = settings.display_utc_offset_hours
        self.offset_preview.setText("" if offset_problem else offset_preview(hours))

        problem = self._problem_text()
        self.problem_label.setText(problem)
        self.problem_label.setStyleSheet(error_style)
        self.problem_label.setVisible(bool(problem))

        self.save_button.setEnabled(
            self.config_path is not None
            and not errors
            and self._hidden_error is None
            and (self.has_changes() or self._read_error is not None or self._file_error is not None)
        )
        self.reload_button.setEnabled(self.config_path is not None)

    # =====================================================================
    # Database
    # =====================================================================

    def _browse_db(self) -> None:
        start = self.db_edit.text().strip()
        path, _filter = QFileDialog.getOpenFileName(self, "Database file", start, DB_FILE_FILTER)
        if path:
            self.db_edit.setText(str(Path(path)))
            self.check_database()

    def _db_edit_finished(self) -> None:
        if self.db_edit.text().strip() != self._checked_path:
            self.check_database()

    def check_database(self) -> None:
        """Check the database path in the field, in a worker. Opens the file read-only."""
        path = self.db_edit.text().strip()
        self._check_id += 1
        check_id = self._check_id
        self._checked_path = path
        if not path:
            self.db_status.setText(NO_DB_PATH)
            return
        self.db_status.setText(f"Checking {path}...")
        self.runner.start(
            lambda task: inspect_database(path),
            on_success=lambda info: self._checked(check_id, database_status_text(info)),
            on_failure=lambda exc: self._checked(check_id, f"Cannot check the file: {exc}"),
        )

    def _checked(self, check_id: int, text: str) -> None:
        if check_id == self._check_id:  # a later check replaces this one
            self.db_status.setText(text)

    # =====================================================================
    # NAS roots
    # =====================================================================

    def _update_root_buttons(self, *_: object) -> None:
        selected = self.roots_list.currentRow() >= 0
        self.edit_root_button.setEnabled(selected)
        self.remove_root_button.setEnabled(selected)

    def add_root(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Add NAS root", "UNC path of the NAS root, for example \\\\server\\share:"
        )
        if ok and text.strip():
            self.roots_list.addItem(QListWidgetItem(text.strip()))
            self.roots_list.setCurrentRow(self.roots_list.count() - 1)
            self._validate()

    def edit_root(self) -> None:
        item = self.roots_list.currentItem()
        if item is None:
            return
        text, ok = QInputDialog.getText(
            self,
            "Edit NAS root",
            "UNC path of the NAS root:",
            QLineEdit.EchoMode.Normal,
            item.text(),
        )
        if ok and text.strip():
            item.setText(text.strip())
            self._validate()

    def remove_root(self) -> None:
        row = self.roots_list.currentRow()
        if row >= 0:
            self.roots_list.takeItem(row)
            self._update_root_buttons()
            self._validate()

    # =====================================================================
    # About
    # =====================================================================

    def open_config_folder(self) -> None:
        if self.config_path is not None and self.config_path.parent.is_dir():
            self._open_folder(self.config_path.parent)

    # =====================================================================
    # Saving
    # =====================================================================

    def save(self) -> None:
        """Write config.toml and emit `saved` (SPEC section 4; O28, O31)."""
        if self.config_path is None or not self.save_button.isEnabled():
            return
        data = merge_settings(self._data or {}, self.current_settings())
        try:
            new_config = parse_config(data, str(self.config_path))
        except ConfigError as exc:
            self.show_message(f"Not saved: {exc}")
            return
        if self.confirm_apply is not None and not self.confirm_apply(new_config):
            self.show_message("Not saved.")
            return
        try:
            config = save_config(self.config_path, data)
        except ConfigError as exc:
            self.show_message(f"Not saved: {exc}")
            return
        self.reload()
        self.show_message(f"Saved {self.config_path}.")
        self.saved.emit(config)
