"""Log recording tab: scan a recording folder and add it to the database.

SPEC section 6. The logic lives in iqdm.entry, which has no Qt. This module builds
the form, runs scans and database work in a TaskRunner, and shows the checklist.
Edit mode follows DECISIONS.md D16. Times are shown at the configured offset from UTC
(D24). fc is MHz (D19); fs takes a unit, Hz by default (D25).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iqdm import bands, batchlog, entry, recorderlog, templates
from iqdm.config import Config
from iqdm.db.connection import DatabaseError
from iqdm.entry import ChannelInput, Choices, EntryInput, ItemState, ParamInput
from iqdm.gui.widgets.checklist import MARKS, ChecklistView, colours_for
from iqdm.gui.widgets.folder_table import FolderRow, FolderTable
from iqdm.gui.widgets.mark_frame import MarkFrame
from iqdm.gui.widgets.param_table import ParamTable
from iqdm.gui.widgets.template_fields import TemplateFieldsDialog
from iqdm.gui.workers import Task, TaskRunner
from iqdm.location import DriveResolver, Location, LocationError, mapped_drive_unc, split_location
from iqdm.models import Endianness, IqLayout, Recording, SameStart, SampleType
from iqdm.scan.scanner import ScanCancelled, ScanError, ScanResult, scan_recording
from iqdm.timeutil import display_time, offset_label

REFRESH_DELAY_MS = 150  # checklist refresh after typing stops
DEFAULT_FILE_DURATION_S = 1.0
FS_FILLED_TOOLTIP = (
    "Filled in from the file size, sample type, header bytes and file duration. "
    "Type a value to replace it."
)
NO_DATABASE = 'No database configured. Set the database path in the "Settings" tab.'
NO_PROJECT = "No project"  # the first entry of the project dropdown (D73)
LOGGED_BY_PLACEHOLDER = "Your name (required)"
SITE_PLACEHOLDER = "Choose a site (required)"
REQUIRED_PLACEHOLDER = "Required"
FS_PLACEHOLDER = "Required, e.g. 10M"
SAVE_BLOCKED_TOOLTIP = 'Complete the items under "Before saving" first.'
FS_TOOLTIP = f"Sample rate: {entry.FREQUENCY_HELP}. A number without a unit is Hz."
READ_ONLY_TOOLTIP = "Filled in by the app. You cannot edit this field."
READ_ONLY_PROPERTY = "iqdmReadOnly"  # marks line edits whose colours follow the theme
BAND_TOOLTIP = (
    "Filled in from fc when fc lies in one of these bands: "
    f"{bands.bands_text()}. Pick or type another band to replace it."
)
TEMPLATE_FILTER = "Templates (*.toml)"
REPLACE_TEMPLATE_TITLE = "Replace the template?"


def band_filled_tooltip(band: bands.Band) -> str:
    return (
        f"Filled in from fc: {band.name} is {band.range_text}. "
        "Pick or type another band to replace it."
    )


def replace_template_question(path: Path) -> str:
    return f"{path} already exists. Replace it with the fields you chose?"


DELETE_TITLE = "Delete this entry?"
DELETE_BUTTON = "Delete entry"
DELETE_TOOLTIP = (
    "Delete this entry from the catalogue, for example a folder logged by mistake. "
    "The files stay. An entry that was archived or copied cannot be deleted."
)
NO_RECORDS_FOLDER = (
    "This entry cannot be deleted here, because the app has no folder for the copy it "
    "saves before a delete."
)


SEVERAL_TOOLTIP = (
    "Log several recording folders with the same set-up. Type the shared fields once; "
    "each folder takes its times, channels and recorder's log values from its own scan."
)
SAVE_FOLDERS_TITLE = "Save the entries?"
DROP_FOLDERS_TITLE = "Drop the folder list?"
NO_FOLDER_SELECTED = "Select a folder in the list to see its checklist."
BATCH_TEMPLATE_CHANNELS_NOTE = (
    "The template's band and fc were not used: each folder takes them from its own scan "
    "and recorder's log."
)
BATCH_TEMPLATE_LOG_NOTE = (
    "Folders whose recorder's log names the sample type, USRP gain, Clock reference or "
    "USRP keep the log's values."
)
PARENT_IS_RECORDING = (
    "This folder is itself a recording: its numbered subfolders are its channels."
)
LOG_ROWS_HEADERS = ("Applies to", "Parameter", "Value", "Unit")
LOG_ROWS_TOOLTIP = (
    "From this folder's recorder's log. To change a value for one folder, untick the "
    'folder in the list and log it with "One folder".'
)


def log_rows_title(folder: str) -> str:
    return f"From the recorder's log of {folder}. These rows are saved with this folder:"


def log_rows_note(shown: batchlog.LogShown, shared_dtype: SampleType) -> str:
    """The line under the log rows: shared rows they replace, and the log's sample type."""
    lines = []
    if shown.replaced:
        rows = "; ".join(_param_text(p) for p in shown.replaced)
        lines.append(f"For this folder they replace these shared rows: {rows}.")
    if shown.dtype is not None and shown.dtype != shared_dtype:
        lines.append(
            f"This folder's log names the sample type {shown.dtype}. The folder is saved "
            "with it, in place of the sample type in section 3."
        )
    return "\n".join(lines)


def _param_text(p: ParamInput) -> str:
    """'USRP gain 20 dB', 'Ch 1: USRP gain 25 dB'."""
    text = " ".join(t for t in (p.param.strip(), p.value.strip(), p.unit.strip()) if t)
    return text if p.channel_index is None else f"Ch {p.channel_index}: {text}"


def drop_folders_question(count: int) -> str:
    folders = "1 folder that is" if count == 1 else f"{count:,} folders that are"
    return f"The list holds {folders} not saved. Drop the list and log one folder?"


def save_button_text(ready: int) -> str:
    """'Save 12 entries': the Save button while several folders are listed."""
    if ready == 0:
        return "Save entries"
    return "Save 1 entry" if ready == 1 else f"Save {ready:,} entries"


def confirm_batch_save(parent: QWidget, text: str) -> bool:
    """Ask before the entries of several folders are saved (D90). Save is the default."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(SAVE_FOLDERS_TITLE)
    box.setText(text)
    save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(save)
    box.setEscapeButton(cancel)
    box.exec()
    return box.clickedButton() is save


def confirm_delete(parent: QWidget, text: str) -> bool:
    """Ask before a delete (D89). Cancel is the default; Esc cancels."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(DELETE_TITLE)
    box.setText(text)
    delete = box.addButton(DELETE_BUTTON, QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    box.exec()
    return box.clickedButton() is delete


CONFLICT_TITLE = "Template and recorder's log differ"
KEEP_LOG_BUTTON = "Keep the log's values"
USE_TEMPLATE_BUTTON = "Use the template's values"


class ConflictChoice(StrEnum):
    """The answer to a template that differs from values the log filled in (D87)."""

    KEEP_LOG = "keep log"
    USE_TEMPLATE = "use template"
    CANCEL = "cancel"


def conflict_question(conflicts: Sequence[recorderlog.Conflict]) -> str:
    lines = "\n".join(
        f"\N{BULLET} {c.what}: log {c.log_text}, template {c.template_text}" for c in conflicts
    )
    return (
        "The recorder's log filled in these values for this folder. The template holds "
        f"other values for them:\n\n{lines}\n\nClick \"Keep the log's values\" or \"Use "
        "the template's values\". Either way, the template fills in its other fields."
    )


def ask_template_conflicts(
    parent: QWidget, conflicts: Sequence[recorderlog.Conflict]
) -> ConflictChoice:
    """Ask which values win. Keep the log's values is the default; Esc cancels."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(CONFLICT_TITLE)
    box.setText(conflict_question(conflicts))
    keep = box.addButton(KEEP_LOG_BUTTON, QMessageBox.ButtonRole.AcceptRole)
    use = box.addButton(USE_TEMPLATE_BUTTON, QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(keep)
    box.setEscapeButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is keep:
        return ConflictChoice.KEEP_LOG
    if clicked is use:
        return ConflictChoice.USE_TEMPLATE
    return ConflictChoice.CANCEL


def channel_headers(zone: str) -> tuple[str, ...]:
    """Channel table headings, with times in the display zone such as 'UTC+8' (D24)."""
    return (
        "Ch",
        "Folder",
        "Band",
        "fc (MHz)",
        "fs",
        f"Start ({zone})",
        f"End ({zone})",
        "Files",
        "Coverage",
    )


def time_text(t: float | None, offset_hours: float) -> str:
    """'2026-09-30 10:00:00' at the display offset, or '' for None (D24)."""
    return "" if t is None else display_time(t, offset_hours)


@dataclass(frozen=True, kw_only=True)
class ScanOutcome:
    """Result of the scan task: the scan and the duplicate check."""

    scan: ScanResult
    logged_id: int | None = None
    duplicate_checked: bool = False
    db_error: str | None = None
    same_start: tuple[SameStart, ...] = ()  # recordings that start with the scan (D61)
    recorder: recorderlog.RecorderLog | None = None  # the recording task's logs (D82)


@dataclass(eq=False)
class _ChannelRow:
    index: int
    band: QComboBox
    fc: QLineEdit
    fs: QLineEdit
    fs_auto: bool = False  # fs holds the value worked out from the file size (D21)
    fc_log: bool = False  # fc came from the recorder's log (D82)
    fs_log: bool = False  # fs came from the recorder's log (D82)
    band_auto: bool = False  # the band was filled in from fc (D88); marks the field only
    fc_before: str = ""  # the fc text the band last followed (D88)
    fc_mark: entry.ChecklistItem | None = None  # fc is empty or wrong (D95)
    fs_mark: entry.ChecklistItem | None = None


class LogTab(QWidget):
    """Form for logging a recording folder, and for editing a logged one."""

    saved = Signal(int)  # recording id after a save, new or edited; the Viewer refreshes
    deleted = Signal(int)  # recording id after a delete (D89)

    def __init__(
        self,
        config: Config | None = None,
        *,
        resolve_drive: DriveResolver | None = mapped_drive_unc,
        runner: TaskRunner | None = None,
        records_folder: Path | None = None,
        deletion_blocked: Callable[[int], str | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """records_folder receives the copy of a deleted entry; without it, edit mode
        cannot delete. deletion_blocked names why another tab holds a recording (D89)."""
        super().__init__(parent)
        self.config = Config() if config is None else config
        self._records_folder = records_folder
        self._deletion_blocked = deletion_blocked
        self._offset = self.config.display_utc_offset_hours
        self._zone = offset_label(self._offset)
        self._resolve_drive = resolve_drive
        self.runner = TaskRunner(self) if runner is None else runner

        self._choices = Choices(sites=[], param_names=[], bands=[])
        self._choices_id = 0
        self._raw_scan: ScanResult | None = None  # at the duration used for the scan
        self._scan: ScanResult | None = None  # at the current duration
        self._location: Location | None = None
        self._location_error: str | None = None
        self._logged_id: int | None = None
        self._duplicate_checked = False
        self._same_start: tuple[SameStart, ...] = ()
        self._original: Recording | None = None
        self._scan_task: Task | None = None
        self._saving = False
        self._channel_rows: list[_ChannelRow] = []
        self._duration_set_by_user = False  # D22: the file names set it until the user does
        self._duration_from_names = False
        # D79: band and fc by channel number, kept for the next folder's scan.
        self._carried: dict[int, ChannelInput] = {}
        self._kept = False  # the form holds values kept from the previous entry (D79)
        self._template_folder = ""  # the folder of the last template file, this session
        self._message: tuple[ItemState | None, str] = (None, "")  # the line under the buttons
        self._recorder: recorderlog.RecorderLog | None = None  # the scanned folder's logs
        self._log_values: recorderlog.FormValues | None = None  # what the log filled in
        self._log_applied_for: str | None = None  # the folder the log filled in for
        # Several folders (D90): the list, the folder shown in section 4, and the work.
        self._folders: list[batchlog.BatchFolder] = []
        self._selected_key: int | None = None
        self._views: list[tuple[batchlog.BatchFolder, batchlog.FolderView]] = []
        self._checks = batchlog.FolderChecks()
        self._batch_task: Task | None = None
        self._parent_recording: Path | None = None  # a parent that is itself a recording

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self.refresh_checklist)

        self._build()
        self.clear_form()
        self.reload_choices()

    # =====================================================================
    # Layout
    # =====================================================================

    def _build(self) -> None:
        form_column = QVBoxLayout()
        form_column.addWidget(self._build_source())
        form_column.addWidget(self._build_recording())
        form_column.addWidget(self._build_format())
        form_column.addWidget(self._build_channels())
        form_column.addWidget(self._build_rf_chain())
        form_column.addStretch(1)
        form_widget = QWidget()
        form_widget.setLayout(form_column)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_widget)

        layout = QHBoxLayout(self)
        layout.addWidget(scroll, 3)
        layout.addWidget(self._build_side_panel(), 1)

    def _build_source(self) -> QGroupBox:
        box = QGroupBox("1 · Source folder")
        self.source_box = box
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Recording folder, local or on the NAS")
        self.folder_edit.textChanged.connect(self._folder_changed)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse)
        self.scan_button = QPushButton("Scan folder")
        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_scan)
        self.cancel_button.setEnabled(False)
        self.scan_summary = QLabel()
        self.scan_summary.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(self.folder_edit, 1)
        row.addWidget(self.browse_button)
        row.addWidget(self.scan_button)
        row.addWidget(self.cancel_button)
        self.one_page = QWidget()
        one_layout = QVBoxLayout(self.one_page)
        one_layout.setContentsMargins(0, 0, 0, 0)
        one_layout.addLayout(row)
        one_layout.addWidget(self.scan_summary)

        self.one_radio = QRadioButton("One folder")
        self.one_radio.setChecked(True)
        self.several_radio = QRadioButton("Several folders")
        self.several_radio.setToolTip(SEVERAL_TOOLTIP)
        self.several_radio.toggled.connect(self._mode_toggled)
        modes = QHBoxLayout()
        modes.addWidget(self.one_radio)
        modes.addWidget(self.several_radio)
        modes.addStretch(1)

        layout = QVBoxLayout(box)
        layout.addLayout(modes)
        layout.addWidget(self.one_page)
        layout.addWidget(self._build_folders())
        return box

    def _build_folders(self) -> QWidget:
        """The list of folders for "Several folders" (D90)."""
        self.several_page = QWidget()
        self.several_page.setVisible(False)
        self.add_folders_button = QPushButton("Add folders...")
        self.add_folders_button.setToolTip(
            "Choose a folder; the recording folders inside it are added to the list."
        )
        self.add_folders_button.clicked.connect(lambda: self.add_folders())
        self.remove_folder_button = QPushButton("Remove")
        self.remove_folder_button.setToolTip("Take the selected folder off the list.")
        self.remove_folder_button.clicked.connect(self.remove_folder)
        self.scan_folders_button = QPushButton("Scan folders")
        self.scan_folders_button.setToolTip("Scan again every folder in the list not yet saved.")
        self.scan_folders_button.clicked.connect(lambda: self.scan_folders())
        self.cancel_folders_button = QPushButton("Cancel")
        self.cancel_folders_button.clicked.connect(self._cancel_batch_task)
        self.folder_table = FolderTable(self._zone)
        self.folder_table.current_changed.connect(self._select_folder)
        self.folder_table.tick_changed.connect(self._tick_folder)
        self.batch_line = QLabel()
        self.batch_line.setWordWrap(True)
        self.add_parent_button = QPushButton("Add it as one recording")
        self.add_parent_button.setVisible(False)
        self.add_parent_button.clicked.connect(self._add_parent_as_one)

        buttons = QHBoxLayout()
        for button in (
            self.add_folders_button,
            self.remove_folder_button,
            self.scan_folders_button,
            self.cancel_folders_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        parent_row = QHBoxLayout()
        parent_row.addWidget(self.batch_line, 1)
        parent_row.addWidget(self.add_parent_button)
        layout = QVBoxLayout(self.several_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(buttons)
        layout.addWidget(self.folder_table)
        layout.addLayout(parent_row)
        return self.several_page

    def _build_recording(self) -> QGroupBox:
        box = QGroupBox("2 · Recording")
        self.start_edit = _read_only()
        self.end_edit = _read_only()
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setDecimals(3)
        self.duration_spin.setRange(0.001, 86400.0)
        self.duration_spin.setSuffix(" s")
        self.duration_spin.valueChanged.connect(self._duration_changed)
        self.logged_by_edit = QLineEdit()
        self.logged_by_edit.setPlaceholderText(LOGGED_BY_PLACEHOLDER)
        self.logged_by_edit.textChanged.connect(self._schedule_refresh)
        self.site_combo = QComboBox()
        self.site_combo.setPlaceholderText(SITE_PLACEHOLDER)
        self.site_combo.currentIndexChanged.connect(self._schedule_refresh)
        self.add_site_button = QPushButton("Add site")
        self.add_site_button.clicked.connect(self.add_site)
        self.project_combo = QComboBox()  # optional (D73); the first entry is no project
        self.project_combo.addItem(NO_PROJECT, None)
        self.project_combo.currentIndexChanged.connect(self._schedule_refresh)
        self.add_project_button = QPushButton("Add project")
        self.add_project_button.clicked.connect(self.add_project)
        self.plan_edit = QLineEdit()
        self.storage_root_edit = _read_only()
        self.rel_path_edit = _read_only()
        self.state_edit = _read_only()
        self.remarks_edit = QPlainTextEdit()
        self.remarks_edit.setPlaceholderText("Anything a future reader should know")
        self.remarks_edit.setFixedHeight(60)

        site_row = QHBoxLayout()
        site_row.addWidget(MarkFrame(self.site_combo), 1)  # its frame marks a missing site
        site_row.addWidget(self.add_site_button)
        project_row = QHBoxLayout()
        project_row.addWidget(self.project_combo, 1)
        project_row.addWidget(self.add_project_button)

        self.start_label = QLabel()
        self.end_label = QLabel()
        self._label_times()

        grid = QGridLayout(box)
        grid.addWidget(self.start_label, 0, 0)
        grid.addWidget(self.end_label, 0, 1)
        grid.addWidget(QLabel("File duration"), 0, 2)
        grid.addWidget(QLabel("Logged by"), 0, 3)
        grid.addWidget(self.start_edit, 1, 0)
        grid.addWidget(self.end_edit, 1, 1)
        grid.addWidget(self.duration_spin, 1, 2)
        grid.addWidget(self.logged_by_edit, 1, 3)
        grid.addWidget(QLabel("Site"), 2, 0)
        grid.addWidget(QLabel("Project (optional)"), 2, 1)
        grid.addWidget(QLabel("Recording plan reference"), 2, 2, 1, 2)
        grid.addLayout(site_row, 3, 0)
        grid.addLayout(project_row, 3, 1)
        grid.addWidget(self.plan_edit, 3, 2, 1, 2)
        grid.addWidget(QLabel("Storage root · from folder"), 4, 0, 1, 2)
        grid.addWidget(QLabel("Relative path"), 4, 2)
        grid.addWidget(QLabel("Archive state"), 4, 3)
        grid.addWidget(self.storage_root_edit, 5, 0, 1, 2)
        grid.addWidget(self.rel_path_edit, 5, 2)
        grid.addWidget(self.state_edit, 5, 3)
        grid.addWidget(QLabel("Remarks (optional)"), 6, 0, 1, 4)
        grid.addWidget(self.remarks_edit, 7, 0, 1, 4)
        return box

    def _label_times(self) -> None:
        self.start_label.setText(f"Start ({self._zone}) · from scan")
        self.end_label.setText(f"End ({self._zone}) · from scan")

    def _build_format(self) -> QGroupBox:
        box = QGroupBox("3 · File format")
        self.dtype_combo = _enum_combo(SampleType)
        self.layout_combo = _enum_combo(IqLayout)
        self.endian_combo = _enum_combo(Endianness)
        self.header_spin = QSpinBox()
        self.header_spin.setRange(0, 2_000_000_000)
        for widget in (self.layout_combo, self.endian_combo):
            widget.currentIndexChanged.connect(self._schedule_refresh)
        # Sample type and header bytes change a filled-in fs (D21).
        self.dtype_combo.currentIndexChanged.connect(self._format_changed)
        self.header_spin.valueChanged.connect(self._format_changed)

        layout = QFormLayout(box)
        layout.addRow("Sample type", self.dtype_combo)
        layout.addRow("IQ layout", self.layout_combo)
        layout.addRow("Endianness", self.endian_combo)
        layout.addRow("Header bytes", self.header_spin)
        return box

    def _build_channels(self) -> QGroupBox:
        box = QGroupBox("4 · Channels")
        headers = channel_headers(self._zone)
        self.channel_table = QTableWidget(0, len(headers))
        self.channel_table.setHorizontalHeaderLabels(headers)
        self.channel_table.verticalHeader().setVisible(False)
        self.channel_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        layout = QVBoxLayout(box)
        layout.addWidget(self.channel_table)
        return box

    def _build_rf_chain(self) -> QGroupBox:
        box = QGroupBox("5 · RF chain")
        self.param_table = ParamTable()
        self.param_table.changed.connect(self._schedule_refresh)
        layout = QVBoxLayout(box)
        layout.addWidget(
            QLabel("Add whatever is relevant; full detail stays in the recording plan.")
        )
        layout.addWidget(self.param_table)
        layout.addWidget(self._build_log_rows())
        return box

    def _build_log_rows(self) -> QWidget:
        """Several folders: the selected folder's rows from its recorder's log (O55)."""
        self.log_rows_label = QLabel()
        self.log_rows_label.setWordWrap(True)
        self.log_rows_table = QTableWidget(0, len(LOG_ROWS_HEADERS))
        self.log_rows_table.setHorizontalHeaderLabels(LOG_ROWS_HEADERS)
        self.log_rows_table.verticalHeader().setVisible(False)
        self.log_rows_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.log_rows_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.log_rows_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.log_rows_table.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.log_rows_table.setToolTip(LOG_ROWS_TOOLTIP)
        header = self.log_rows_table.horizontalHeader()
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self.log_rows_note = QLabel()
        self.log_rows_note.setWordWrap(True)
        self.log_rows_box = QWidget()
        layout = QVBoxLayout(self.log_rows_box)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.addWidget(self.log_rows_label)
        layout.addWidget(self.log_rows_table)
        layout.addWidget(self.log_rows_note)
        self.log_rows_box.setVisible(False)
        return self.log_rows_box

    def _build_side_panel(self) -> QGroupBox:
        box = QGroupBox("Before saving")
        self.mode_label = QLabel()
        self.checklist = ChecklistView()
        self.folder_label = QLabel()  # several folders: the selected folder (D90)
        self.folder_label.setWordWrap(True)
        self.folder_checklist = ChecklistView()
        self.folder_label.setVisible(False)
        self.folder_checklist.setVisible(False)
        self.state_note = QLabel()
        self.state_note.setWordWrap(True)
        self.kept_note = QLabel()  # D79: what a new folder kept from the previous entry
        self.kept_note.setWordWrap(True)
        self.kept_note.setVisible(False)
        self.edit_existing_button = QPushButton("Edit existing entry")
        self.edit_existing_button.clicked.connect(self._edit_existing)
        self.use_parent_button = QPushButton("Use parent folder")
        self.use_parent_button.clicked.connect(self._use_parent_folder)
        self.save_button = QPushButton("Save entry")
        self.save_button.clicked.connect(self.save)
        self.clear_button = QPushButton("Clear form")
        self.clear_button.clicked.connect(self.clear_form)
        self.delete_button = QPushButton("Delete entry...")  # edit mode only (D89)
        self.delete_button.setToolTip(DELETE_TOOLTIP)
        self.delete_button.clicked.connect(self.delete_entry)
        self.import_button = QPushButton("Import template...")
        self.import_button.setToolTip("Fill in the form from a template file.")
        self.import_button.clicked.connect(lambda: self.import_template())
        self.export_button = QPushButton("Export template...")
        self.export_button.setToolTip("Save fields of this form to a template file.")
        self.export_button.clicked.connect(lambda: self.export_template())
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        template_buttons = QHBoxLayout()
        template_buttons.addWidget(self.import_button, 1)
        template_buttons.addWidget(self.export_button, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button, 1)
        buttons.addWidget(self.clear_button)
        layout = QVBoxLayout(box)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.kept_note)
        layout.addWidget(self.checklist, 1)
        layout.addWidget(self.folder_label)
        layout.addWidget(self.folder_checklist, 1)
        layout.addWidget(self.edit_existing_button)
        layout.addWidget(self.use_parent_button)
        layout.addWidget(self.state_note)
        layout.addLayout(template_buttons)
        layout.addLayout(buttons)
        layout.addWidget(self.delete_button)
        layout.addWidget(self.message_label)
        return box

    # =====================================================================
    # Form state
    # =====================================================================

    @property
    def editing(self) -> Recording | None:
        """The stored recording in edit mode, else None."""
        return self._original

    @property
    def scan(self) -> ScanResult | None:
        """The current scan at the current file duration, or None."""
        return self._scan

    @property
    def batch_mode(self) -> bool:
        """True in "Several folders" mode (D90)."""
        return self.several_radio.isChecked()

    @property
    def folders(self) -> list[batchlog.BatchFolder]:
        return list(self._folders)

    def unsaved_folders(self) -> int:
        """The number of listed folders not yet saved (D90)."""
        return sum(1 for f in self._folders if not f.saved)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802  (Qt override)
        """Follow a switch between the light and dark theme."""
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        ):
            _restyle_fields(self)
            if event.type() != QEvent.Type.StyleChange:
                _restyle_sheets(self)
            if hasattr(self, "kept_note"):  # the palette can change before _build ends
                self._show_kept_note()
                self._show_message()
                self._schedule_refresh()  # the field marks take the theme's colours (D95)
        super().changeEvent(event)

    # =====================================================================
    # New configuration from the Settings tab (Milestone 3a, O28)
    # =====================================================================

    @property
    def is_saving(self) -> bool:
        """True while a save runs in the worker."""
        return self._saving

    def has_unsaved_input(self) -> bool:
        """True in edit mode, or when the form holds a folder, a folder not yet saved in
        the list (D90), a plan reference, remarks or an RF chain row with text."""
        return (
            self._original is not None
            or bool(self.folder_edit.text().strip())
            or self.unsaved_folders() > 0
            or bool(self.plan_edit.text().strip())
            or bool(self.remarks_edit.toPlainText().strip())
            or any(
                p.param.strip() or p.value.strip() or p.unit.strip()
                for p in self.param_table.rows()
            )
        )

    def apply_clears_form(self, config: Config) -> bool:
        """True when `config` changes db_path or nas_roots, so apply_config() clears the form.

        The folder location, the duplicate check and edit mode all depend on these two
        keys.
        """
        return config.db_path != self.config.db_path or config.nas_roots != self.config.nas_roots

    def apply_config(self, config: Config) -> None:
        """Take a new configuration without a restart (O28).

        A new display offset redraws the times and keeps the form. A new db_path or new
        NAS roots clear the form and reload the lists. The caller asks the user first
        when has_unsaved_input() is True.
        """
        clears = self.apply_clears_form(config)
        self.config = config
        if config.display_utc_offset_hours != self._offset:
            self._offset = config.display_utc_offset_hours
            self._zone = offset_label(self._offset)
            self._label_times()
            self.channel_table.setHorizontalHeaderLabels(channel_headers(self._zone))
            self.folder_table.set_zone(self._zone)
            if self.batch_mode:
                self._show_selected()
            elif self._scan is not None:
                self._show_scan()
            elif self._original is not None:
                self._show_stored_channels(self._original, self._inputs_by_index())
        if clears:
            self._choices_id += 1  # drop lists still loading from the old database
            self._choices_loaded(Choices(sites=[], param_names=[], bands=[]), None, None)
            self.clear_form()
            self.reload_choices()
        else:
            self.refresh_checklist()

    def show_message(self, text: str, state: ItemState | None = None) -> None:
        """The line under the buttons. A state adds its mark and colour (D84)."""
        self._message = (state, text)
        self._show_message()

    @property
    def message_text(self) -> str:
        """The message line's text, without its mark."""
        return self._message[1]

    @property
    def message_state(self) -> ItemState | None:
        return self._message[0]

    def _show_message(self) -> None:
        state, text = self._message
        if state is None or not text:
            self.message_label.setText(text)
            self.message_label.setStyleSheet("")
            return
        self.message_label.setText(f"{MARKS[state]}  {text}")
        colour = colours_for(self.palette())[state]
        self.message_label.setStyleSheet(f"color: {colour.name()};")

    def current_input(self) -> EntryInput:
        return EntryInput(
            logged_by=self.logged_by_edit.text(),
            site_id=self.site_combo.currentData(),
            project_id=self.project_combo.currentData(),
            recording_plan_ref=self.plan_edit.text(),
            remarks=self.remarks_edit.toPlainText(),
            file_duration_s=self.duration_spin.value(),
            file_duration_inferred=self._duration_from_names,
            dtype=self.dtype_combo.currentData(),
            iq_layout=self.layout_combo.currentData(),
            endianness=self.endian_combo.currentData(),
            header_bytes=self.header_spin.value(),
            channels=[
                ChannelInput(
                    channel_index=r.index,
                    band=r.band.currentText(),
                    fc_mhz=r.fc.text(),
                    fs_text=r.fs.text(),
                    fs_inferred=r.fs_auto,
                    fc_from_log=r.fc_log,
                    fs_from_log=r.fs_log,
                    band_from_fc=r.band_auto,
                )
                for r in self._channel_rows
            ],
            params=self.param_table.rows(),
        )

    def channel_widgets(self, index: int) -> tuple[QComboBox, QLineEdit, QLineEdit]:
        """Band, fc and fs widgets of one channel row, for tests."""
        row = next(r for r in self._channel_rows if r.index == index)
        return row.band, row.fc, row.fs

    def clear_form(self) -> None:
        """Back to an empty new entry. In "Several folders" mode the list is emptied."""
        self.cancel_scan()
        self._original = None
        self._clear_scan()
        self._clear_folders()
        _set_read_only(self.folder_edit, False)
        self.browse_button.setEnabled(True)
        self.folder_edit.blockSignals(True)
        self.folder_edit.clear()
        self.folder_edit.blockSignals(False)
        self._set_location(None, None)
        self.logged_by_edit.clear()  # typed by the user; the Windows login may name nobody (D94)
        self.site_combo.setCurrentIndex(-1)
        self.project_combo.setCurrentIndex(0)  # no project
        self.plan_edit.clear()
        self.remarks_edit.clear()
        self._reset_all_fields()
        self.mode_label.setText("New entry")
        self.show_message("" if self.config.db_path else NO_DATABASE, ItemState.TODO)
        self.refresh_checklist()

    def _reset_all_fields(self) -> None:
        """Defaults for the format, channel and RF chain fields, for Clear form (D79)."""
        self._reset_scan_fields()
        self._carried = {}
        self._kept = False
        self.dtype_combo.setCurrentIndex(self.dtype_combo.findData(SampleType.INT16))
        self.layout_combo.setCurrentIndex(self.layout_combo.findData(IqLayout.INTERLEAVED_IQ))
        self.endian_combo.setCurrentIndex(self.endian_combo.findData(Endianness.LITTLE))
        self.header_spin.setValue(0)
        self.param_table.set_rows([])

    def _reset_scan_fields(self) -> None:
        """Clear what the scan of a folder gives: the file duration and the channel rows.

        A new folder keeps everything else (DECISIONS.md D79). fs comes from the next
        scan (D21) and the file duration from its file names (D22).
        """
        self._set_duration(DEFAULT_FILE_DURATION_S)
        self._duration_set_by_user = False
        self._duration_from_names = False
        self._set_channel_rows([], {})

    def _carry_channel_inputs(self) -> None:
        """Keep the band and fc of each channel row for the next folder (D79)."""
        for c in self.current_input().channels:
            if c.band.strip() or c.fc_mhz.strip():
                self._carried[c.channel_index] = ChannelInput(
                    channel_index=c.channel_index,
                    band=c.band,
                    fc_mhz=c.fc_mhz,
                    band_from_fc=c.band_from_fc,
                )
            else:
                self._carried.pop(c.channel_index, None)

    def _kept_channel_count(self) -> int:
        typed = {
            c.channel_index
            for c in self.current_input().channels
            if c.band.strip() or c.fc_mhz.strip()
        }
        return len(typed | set(self._carried))

    def _drop_settings_of_missing_channels(self, scan: ScanResult) -> None:
        """Remove kept values of channels the new folder lacks, and say so (D79)."""
        present = {c.channel_index for c in scan.channels}
        gone = sorted(i for i in self._carried if i not in present)
        for i in gone:
            del self._carried[i]
        rows = self.param_table.rows()
        kept = [p for p in rows if p.channel_index is None or p.channel_index in present]
        removed_rows = [p for p in rows if p not in kept]
        if removed_rows:
            self.param_table.set_rows(kept)
        channels = sorted(set(gone) | {p.channel_index for p in removed_rows})
        if channels:
            self.show_message(
                entry.missing_channels_text(
                    channels, bool(gone), sum(1 for p in removed_rows if not p.is_blank)
                ),
                ItemState.INFO,
            )

    def _clear_scan(self) -> None:
        self._raw_scan = None
        self._scan = None
        self._recorder = None  # D82
        self._log_values: recorderlog.FormValues | None = None
        self._log_applied_for: str | None = None
        self._logged_id = None
        self._duplicate_checked = False
        self._same_start = ()
        self._scan_problems: tuple[str, ...] = ()
        self.scan_summary.clear()
        self.start_edit.clear()
        self.end_edit.clear()

    def _set_location(self, location: Location | None, error: str | None) -> None:
        self._location = location
        self._location_error = error
        self.storage_root_edit.setText(location.storage_root if location else "")
        self.rel_path_edit.setText(location.rel_path if location else "")
        self.state_edit.setText(str(location.archive_state) if location else "")
        self.state_note.setText(entry.state_note(location, self._original))
        self.use_parent_button.setVisible(self._channel_like_parent() is not None)

    def _folder_changed(self, text: str) -> None:
        if self._original is not None:
            return
        self._carry_channel_inputs()
        self._kept = entry.has_kept_values(self.current_input(), self._kept_channel_count())
        self.cancel_scan()
        self._clear_scan()
        self._clear_message()
        self._reset_scan_fields()
        if not text.strip():
            self._set_location(None, None)
        else:
            try:
                location = split_location(text, self.config.nas_roots, self._resolve_drive)
            except LocationError as exc:
                self._set_location(None, str(exc))
            else:
                self._set_location(location, None)
        self._schedule_refresh()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Recording folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(str(Path(folder)))

    def _set_duration(self, value: float) -> None:
        """Set the duration field without counting it as the user's choice."""
        self.duration_spin.blockSignals(True)
        self.duration_spin.setValue(value)
        self.duration_spin.blockSignals(False)

    def _duration_changed(self, value: float) -> None:
        """The user changed the file duration. The file names no longer set it (D22)."""
        self._duration_set_by_user = True
        self._duration_from_names = False
        if self._raw_scan is not None:
            self._scan = entry.with_file_duration(self._raw_scan, value)
            self._show_scan()
        self._schedule_refresh()

    def _format_changed(self, *_: object) -> None:
        self._fill_inferred_fs()
        if self.batch_mode:  # the selected folder's filled-in fs follows (D21)
            self._sync_selected()
            self._show_selected()
        self._schedule_refresh()

    # =====================================================================
    # Channel table
    # =====================================================================

    def _inputs_by_index(self) -> dict[int, ChannelInput]:
        """Typed channel values, with band and fc kept from the previous folder (D79)."""
        typed = {c.channel_index: c for c in self.current_input().channels}
        return {**self._carried, **typed} if self._original is None else typed

    def _set_channel_rows(
        self,
        rows: Sequence[tuple[int, str, float | None, float | None, int | None]],
        inputs: dict[int, ChannelInput],
    ) -> None:
        """Rows of (index, sub_path, start, end, n_files); inputs keep typed values."""
        self.channel_table.setRowCount(0)
        self._channel_rows = []
        duration = self.duration_spin.value()
        for position, (index, sub_path, start, end, n_files) in enumerate(rows):
            inp = inputs.get(index, ChannelInput(channel_index=index))
            band = QComboBox()
            band.setEditable(True)
            band.addItems(entry.band_choices(self._choices.bands))
            # A new entry's empty band takes the band of a kept or template fc (D88).
            # Edit mode shows the stored band as it is.
            filled = (
                entry.band_for_fc(inp.fc_mhz)
                if self._original is None and not inp.band.strip()
                else None
            )
            band.setCurrentText(inp.band if filled is None else filled.name)
            fc = QLineEdit(inp.fc_mhz)
            fc.setPlaceholderText(REQUIRED_PLACEHOLDER)
            fs = QLineEdit(inp.fs_text)
            fs.setPlaceholderText(FS_PLACEHOLDER)
            row = _ChannelRow(
                index=index,
                band=band,
                fc=fc,
                fs=fs,
                fs_auto=inp.fs_inferred,
                fc_log=inp.fc_from_log,
                fs_log=inp.fs_from_log,
                band_auto=inp.band_from_fc or filled is not None,
                fc_before=inp.fc_mhz,
            )
            _mark_fs(row)
            _mark_fc(row)
            _mark_band(row)
            band.currentTextChanged.connect(self._schedule_refresh)
            band.lineEdit().textEdited.connect(lambda _text, r=row: self._band_chosen(r))
            band.activated.connect(lambda _index, r=row: self._band_chosen(r))
            fc.textChanged.connect(lambda text, r=row: self._fc_changed(r, text))
            fs.textChanged.connect(self._schedule_refresh)
            fs.textEdited.connect(lambda _text, r=row: self._fs_typed(r))
            fc.textEdited.connect(lambda _text, r=row: self._fc_typed(r))
            self.channel_table.insertRow(position)
            coverage = ""
            if n_files is not None and start is not None and end is not None and end > start:
                coverage = f"{100 * n_files * duration / (end - start):.1f}%"
            cells = (
                str(index),
                sub_path or "(recording folder)",
                None,
                None,
                None,
                time_text(start, self._offset),
                time_text(end, self._offset),
                "" if n_files is None else f"{n_files:,}",
                coverage,
            )
            for col, text in enumerate(cells):
                if text is not None:
                    self.channel_table.setItem(position, col, _cell(text))
            self.channel_table.setCellWidget(position, 2, band)
            self.channel_table.setCellWidget(position, 3, fc)
            self.channel_table.setCellWidget(position, 4, fs)
            self._channel_rows.append(row)
        self.param_table.set_channels([r.index for r in self._channel_rows])

    def _fs_typed(self, row: _ChannelRow) -> None:
        """The user typed in an fs field. It keeps that value from now on (D21)."""
        row.fs_auto = False
        row.fs_log = False
        _mark_fs(row)

    def _fc_typed(self, row: _ChannelRow) -> None:
        """The user typed in an fc field: it no longer shows as from the log (D82)."""
        row.fc_log = False
        _mark_fc(row)

    def _fc_changed(self, row: _ChannelRow, text: str) -> None:
        """fc changed, typed or set by the log or a template (D88).

        An empty band, or the band of the previous fc, follows the new fc. A band the
        user chose that differs from the previous fc's band stays.
        """
        new = entry.follow_band(row.band.currentText(), row.fc_before, text)
        row.fc_before = text
        if new is not None and new != row.band.currentText().strip():
            row.band.setCurrentText(new)
            row.band_auto = bool(new)
            _mark_band(row)
        self._schedule_refresh()

    def _band_chosen(self, row: _ChannelRow) -> None:
        """The user typed or picked a band: it no longer shows as filled in (D88)."""
        row.band_auto = False
        _mark_band(row)

    def _apply_recorder_log(self) -> None:
        """Fill values from the recorder's log, once per folder of a new entry (D82).

        Log values replace values kept from the previous folder or set by a template.
        A rescan of the same folder does not fill again, so edits after the first scan
        stay. Edit mode never fills.
        """
        log = self._recorder
        folder = self.folder_edit.text().strip()
        if log is None or not log.found or self._original is not None:
            return
        if self._log_applied_for == folder:
            return
        self._log_applied_for = folder
        values = recorderlog.form_values(
            log,
            [r.index for r in self._channel_rows],
            self.param_table.rows(),
            self._choices.param_names,
        )
        if values.dtype is not None:
            self.dtype_combo.setCurrentIndex(self.dtype_combo.findData(values.dtype))
        for row in self._channel_rows:
            if row.index in values.fc_mhz:
                row.fc.setText(values.fc_mhz[row.index])
                row.fc_log = True
                _mark_fc(row)
            if row.index in values.fs_text:
                row.fs.setText(values.fs_text[row.index])
                row.fs_auto = False
                row.fs_log = True
                _mark_fs(row)
        if values.params:
            self.param_table.set_rows(
                recorderlog.merge_params(self.param_table.rows(), values.params)
            )
        self._log_values = values

    def _fill_inferred_fs(self) -> None:
        """Fill fs from the file size where the field is empty or was filled in (D21)."""
        scan = self._scan
        if scan is None:
            return
        by_index = {c.channel_index: c for c in scan.channels}
        for row in self._channel_rows:
            channel = by_index.get(row.index)
            if channel is None or not (row.fs_auto or not row.fs.text().strip()):
                continue
            result = entry.infer_fs(
                channel,
                dtype=self.dtype_combo.currentData(),
                header_bytes=self.header_spin.value(),
                file_duration_s=self.duration_spin.value(),
            )
            row.fs.setText("" if result.fs_hz is None else entry.format_frequency(result.fs_hz))
            row.fs_auto = result.fs_hz is not None
            _mark_fs(row)

    def _show_scan(self) -> None:
        """Fill the channel table, times and summary from the current scan."""
        scan = self._scan
        if scan is None:
            return
        self._set_channel_rows(
            [
                (c.channel_index, c.sub_path, c.start_unix, c.end_unix, c.n_files)
                for c in scan.channels
            ],
            self._inputs_by_index(),
        )
        self._fill_inferred_fs()
        starts = [c.start_unix for c in scan.channels if c.start_unix is not None]
        ends = [c.end_unix for c in scan.channels if c.end_unix is not None]
        self.start_edit.setText(time_text(min(starts), self._offset) if starts else "")
        self.end_edit.setText(time_text(max(ends), self._offset) if ends else "")
        self.scan_summary.setText(scan_summary(scan, self._offset))

    def _show_stored_channels(
        self, rec: Recording, inputs: dict[int, ChannelInput] | None = None
    ) -> None:
        """Channel rows and times of a stored recording. `inputs` keep typed values."""
        if inputs is None:
            inputs = {c.channel_index: c for c in entry.input_from_recording(rec).channels}
        self._set_channel_rows(
            [
                (c.channel_index, c.sub_path, c.start_unix, c.end_unix, c.n_files)
                for c in rec.channels
            ],
            inputs,
        )
        self.start_edit.setText(time_text(rec.start_unix, self._offset))
        self.end_edit.setText(time_text(rec.end_unix, self._offset))

    # =====================================================================
    # Checklist
    # =====================================================================

    def _schedule_refresh(self, *_: object) -> None:
        self._refresh_timer.start()

    def refresh_checklist(self) -> None:
        self._refresh_timer.stop()
        if self.batch_mode:
            self._refresh_folders()
            return
        form = self.current_input()
        filled = (
            () if self._log_values is None else recorderlog.still_filled(self._log_values, form)
        )
        items = entry.checklist(
            form,
            scan=self._scan,
            location=self._location,
            location_error=self._location_error,
            logged_id=self._logged_id,
            duplicate_checked=self._duplicate_checked,
            original=self._original,
            scan_problems=self._scan_problems,
            known_param_names=self._choices.param_names,
            same_start=self._same_start,
            extra_items=recorderlog.checklist_items(self._recorder, self._scan, filled),
        )
        self.checklist.set_items(items)
        self._show_field_marks(known=self._scan is not None or self._original is not None)
        self._show_kept_note()
        self.state_note.setText(entry.state_note(self._location, self._original))
        self.edit_existing_button.setVisible(self._original is None and self._logged_id is not None)
        self.use_parent_button.setVisible(self._channel_like_parent() is not None)
        self._update_buttons()

    def _show_field_marks(self, *, known: bool) -> None:
        """Frame the fields that the checklist names as to do or wrong (D95).

        known is False before the channels are known, as the checklist then does not
        check the RF chain rows' channels (D79). In "Several folders" mode the marks
        cover the shared fields and the selected folder's channels.
        """
        form = self.current_input()
        indices = [r.index for r in self._channel_rows]
        marks = entry.field_marks(form, indices if known else None)
        name = entry.FieldName
        _show_mark(self.logged_by_edit, marks.get((name.LOGGED_BY, None)))
        _show_mark(self.site_combo, marks.get((name.SITE, None)))
        for row in self._channel_rows:
            row.fc_mark = marks.get((name.FC, row.index))
            row.fs_mark = marks.get((name.FS, row.index))
            _mark_fc(row)
            _mark_fs(row)
        for position in range(len(form.params)):
            applies_to, param, value, _unit = self.param_table.row_widgets(position)
            _show_mark(applies_to, marks.get((name.APPLIES_TO, position)))
            for edit, key in ((param, name.PARAM), (value, name.VALUE)):
                mark = marks.get((key, position))
                _show_mark(edit, mark)
                edit.setPlaceholderText(REQUIRED_PLACEHOLDER if mark is not None else "")

    def field_mark(self, widget: QWidget) -> str:
        """A field's mark, "todo", "error" or "", for tests."""
        return str(widget.property(MARK_PROPERTY) or "")

    def _show_kept_note(self) -> None:
        """The information note on values kept from the previous entry (D79)."""
        show = self._kept and self._original is None
        self.kept_note.setVisible(show)
        if not show:
            self.kept_note.setText("")
            return
        note = entry.kept_note(self.current_input(), self._kept_channel_count())
        self.kept_note.setText(f"{MARKS[ItemState.INFO]}  {note}")
        colour = colours_for(self.palette())[ItemState.INFO]
        self.kept_note.setStyleSheet(f"color: {colour.name()};")

    def _update_buttons(self) -> None:
        scanning = self._scan_task is not None or self._batch_task is not None
        self.scan_button.setEnabled(not scanning and not self._saving)
        self.cancel_button.setEnabled(self._scan_task is not None)
        if self.batch_mode:
            ready = sum(1 for f, v in self._views if batchlog.is_ready(f, v.items))
            self.save_button.setText(save_button_text(ready))
            can_save = ready > 0
        else:
            self.save_button.setText("Save entry")
            can_save = entry.can_save(self.checklist.items)
        self.save_button.setEnabled(
            bool(self.config.db_path) and not scanning and not self._saving and can_save
        )
        self.save_button.setToolTip("" if can_save else SAVE_BLOCKED_TOOLTIP)
        self.delete_button.setVisible(self._original is not None)
        self.delete_button.setEnabled(
            bool(self.config.db_path) and not scanning and not self._saving
        )
        idle = not scanning and not self._saving
        for radio in (self.one_radio, self.several_radio):
            radio.setEnabled(idle and self._original is None)
        self.add_folders_button.setEnabled(idle)
        self.remove_folder_button.setEnabled(idle and self._selected_key is not None)
        self.scan_folders_button.setEnabled(idle and self.unsaved_folders() > 0)
        self.cancel_folders_button.setEnabled(self._batch_task is not None and not self._saving)

    # =====================================================================
    # Database lists
    # =====================================================================

    def reload_choices(
        self, select_site: int | None = None, select_project: int | None = None
    ) -> None:
        """Load sites, projects, parameter names and bands in a worker."""
        db = self.config.db_path
        if not db:
            return
        keep = self.site_combo.currentData() if select_site is None else select_site
        keep_project = (
            self.project_combo.currentData() if select_project is None else select_project
        )
        self._choices_id += 1
        choices_id = self._choices_id  # a later reload replaces this one

        def loaded(result: Choices) -> None:
            if choices_id == self._choices_id:
                self._choices_loaded(result, keep, keep_project)

        self.runner.start(
            lambda task: entry.load_choices(db),
            on_success=loaded,
            on_failure=lambda exc: self.show_message(
                f"Cannot read the database: {exc}", ItemState.ERROR
            ),
        )

    def _choices_loaded(
        self, choices: Choices, select_site: int | None, select_project: int | None
    ) -> None:
        self._choices = choices
        self.site_combo.blockSignals(True)
        self.site_combo.clear()
        for site in choices.sites:
            self.site_combo.addItem(site.name, site.id)
        self.site_combo.setCurrentIndex(self.site_combo.findData(select_site))
        self.site_combo.blockSignals(False)
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem(NO_PROJECT, None)
        for project in choices.projects:
            self.project_combo.addItem(project.name, project.id)
        self._select_project(select_project)
        self.project_combo.blockSignals(False)
        self.param_table.set_param_names(choices.param_names)
        for row in self._channel_rows:
            text = row.band.currentText()
            row.band.blockSignals(True)
            row.band.clear()
            row.band.addItems(entry.band_choices(choices.bands))
            row.band.setCurrentText(text)
            row.band.blockSignals(False)
        self.refresh_checklist()

    def add_site(self) -> None:
        db = self.config.db_path
        if not db:
            self.show_message(NO_DATABASE, ItemState.TODO)
            return
        name, ok = QInputDialog.getText(self, "Add site", "Site name:")
        if not ok or not name.strip():
            return
        self.runner.start(
            lambda task: entry.add_site(db, name),
            on_success=lambda site: self._site_added(site),
            on_failure=lambda exc: self.show_message(f"Site not added: {exc}", ItemState.ERROR),
        )

    def _site_added(self, site: object) -> None:
        site_id = getattr(site, "id", None)
        self.show_message(f"Added site {getattr(site, 'name', '')}.", ItemState.OK)
        self.reload_choices(select_site=site_id)

    def _select_project(self, project_id: int | None) -> None:
        """Select a project by id; None or an id not in the list selects no project."""
        index = 0 if project_id is None else self.project_combo.findData(project_id)
        self.project_combo.setCurrentIndex(max(index, 0))

    def add_project(self) -> None:
        db = self.config.db_path
        if not db:
            self.show_message(NO_DATABASE, ItemState.TODO)
            return
        name, ok = QInputDialog.getText(self, "Add project", "Project name:")
        if not ok or not name.strip():
            return
        self.runner.start(
            lambda task: entry.add_project(db, name),
            on_success=lambda project: self._project_added(project),
            on_failure=lambda exc: self.show_message(
                f"Project not added: {exc}", ItemState.ERROR
            ),
        )

    def _project_added(self, project: object) -> None:
        self.show_message(f"Added project {getattr(project, 'name', '')}.", ItemState.OK)
        self.reload_choices(select_project=getattr(project, "id", None))

    # =====================================================================
    # Scanning
    # =====================================================================

    def start_scan(self) -> None:
        if self._scan_task is not None or self._saving:
            return
        folder = self.folder_edit.text().strip()
        if not folder:
            self.show_message("Choose a folder first.", ItemState.TODO)
            return
        if self._original is None and self._location is None:
            self.show_message(f"Folder cannot be logged: {self._location_error}", ItemState.ERROR)
            return
        duration = self.duration_spin.value()
        db = self.config.db_path
        location = self._location if self._original is None else None

        def work(task: Task) -> ScanOutcome:
            scan = scan_recording(
                Path(folder), duration, progress=task.report, cancelled=task.is_cancelled
            )
            log = recorderlog.read_folder(Path(folder), [f.name for f in scan.side_files])
            if location is None or not db:
                return ScanOutcome(scan=scan, recorder=log)
            try:
                logged = entry.find_logged(db, location)
                same = tuple(entry.find_same_start(db, scan))
            except (DatabaseError, OSError) as exc:
                return ScanOutcome(scan=scan, db_error=str(exc), recorder=log)
            return ScanOutcome(
                scan=scan,
                logged_id=logged,
                duplicate_checked=True,
                same_start=same,
                recorder=log,
            )

        self._clear_message()
        self.scan_summary.setText("Scanning...")
        self._scan_task = self.runner.start(
            work,
            on_success=self._scan_finished,
            on_failure=self._scan_failed,
            on_progress=lambda n: self.scan_summary.setText(f"Scanning: {n:,} files found"),
        )
        self._update_buttons()

    def cancel_scan(self) -> None:
        if self._scan_task is not None:
            self._scan_task.cancel()

    def _scan_finished(self, outcome: ScanOutcome) -> None:
        self._scan_task = None
        self._raw_scan = outcome.scan
        if self._original is None and not self._duration_set_by_user:
            self._duration_from_file_names(outcome.scan)
        self._scan = entry.with_file_duration(outcome.scan, self.duration_spin.value())
        self._logged_id = outcome.logged_id
        self._duplicate_checked = outcome.duplicate_checked
        self._same_start = outcome.same_start
        self._recorder = outcome.recorder
        self._show_scan()
        if self._original is None:
            # Before the log fills in, so a kept row of a missing channel, such as a
            # "USRP" row, does not stop the log's row (review of 1.1.0, finding 8).
            self._drop_settings_of_missing_channels(outcome.scan)
        self._apply_recorder_log()
        if outcome.db_error is not None:
            self.show_message(
                f"Cannot check the database for this folder: {outcome.db_error}", ItemState.ERROR
            )
        if self._original is not None:
            self._drop_rows_of_removed_channels(self._original, outcome.scan)
        self.refresh_checklist()

    def _drop_rows_of_removed_channels(self, original: Recording, scan: ScanResult) -> None:
        """Remove RF chain rows of channels the rescan no longer finds (DECISIONS.md D20).

        The save still asks before it removes the channels from the database (D16).
        """
        removed = entry.channel_set_change(original, scan).removed
        rows = self.param_table.rows()
        kept = entry.params_without_channels(rows, removed)
        if len(kept) == len(rows):
            return
        self.param_table.set_rows(kept)
        n = len(rows) - len(kept)
        channels = ", ".join(str(i) for i in removed)
        self.show_message(
            f"The rescan no longer finds channel {channels}. "
            f"{n} RF chain row{'' if n == 1 else 's'} of "
            f"{'that channel' if len(removed) == 1 else 'those channels'} "
            f"{'was' if n == 1 else 'were'} removed from the form. Saving asks for "
            "confirmation.",
            ItemState.INFO,
        )

    def _duration_from_file_names(self, scan: ScanResult) -> None:
        """Set the file duration to the spacing of the file names (D22).

        The default, 1 s, gets no information line. A spacing outside the field's
        range leaves the field as it is, and the checklist reports the mismatch.
        """
        spacing = entry.typical_spacing(scan)
        low, high = self.duration_spin.minimum(), self.duration_spin.maximum()
        if spacing is None or not low <= spacing <= high:
            return
        self._set_duration(spacing)
        self._duration_from_names = spacing != DEFAULT_FILE_DURATION_S

    def _scan_failed(self, exc: Exception) -> None:
        self._scan_task = None
        self._clear_scan()
        if self._original is not None:
            self._show_stored_channels(self._original)
        if isinstance(exc, ScanCancelled):
            self.scan_summary.setText("Scan cancelled.")
        elif isinstance(exc, ScanError):
            self._scan_problems = exc.problems
            self.scan_summary.setText("Scan stopped:\n" + "\n".join(exc.problems))
        else:
            self._scan_problems = (str(exc),)
            self.scan_summary.setText(f"Scan failed: {exc}")
        self.refresh_checklist()

    # =====================================================================
    # Saving and edit mode
    # =====================================================================

    def save(self) -> None:
        self.refresh_checklist()
        db = self.config.db_path
        if not db or self._saving or self._scan_task is not None:
            return
        if self.batch_mode:
            self._save_folders(db)
            return
        if not entry.can_save(self.checklist.items):
            self.show_message("Complete or fix the items in the checklist first.", ItemState.TODO)
            return
        try:
            rec = entry.build_recording(
                self.current_input(),
                scan=self._scan,
                location=self._location,
                original=self._original,
                known_param_names=self._choices.param_names,
            )
        except ValueError as exc:
            self.show_message(f"Not saved: {exc}", ItemState.ERROR)
            return

        original = self._original
        if original is None:
            self._start_save(lambda task: entry.save_new(db, rec), self._saved_new)
            return
        if entry.edit_changes_nothing(original, rec):
            # Keeps the last-changed time (D47).
            self.show_message("No changes to save.", ItemState.INFO)
            return
        allow_removal = False
        if self._scan is not None:
            removed = entry.channel_set_change(original, self._scan).removed
            if removed:
                if not self._confirm_removal(original, removed):
                    self.show_message(
                        "Nothing saved. The channels and their RF chain rows stay in the "
                        "database. Open the entry again to see the stored rows.",
                        ItemState.INFO,
                    )
                    return
                allow_removal = True
        self._start_save(
            lambda task: entry.save_edit(
                db, rec, original=original, allow_channel_removal=allow_removal
            ),
            lambda result: self._saved_edit(original.id),
        )

    def _confirm_removal(self, original: Recording, removed: Sequence[int]) -> bool:
        n_params = entry.params_on_channels(original, removed)
        channels = ", ".join(str(i) for i in removed)
        answer = QMessageBox.question(
            self,
            "Remove channels",
            f"The rescan no longer finds channel {channels}. Saving removes "
            f"{'it' if len(removed) == 1 else 'them'} from recording {original.id}, "
            f"with {n_params} RF chain parameter{'' if n_params == 1 else 's'}.\n\n"
            "Remove and save?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _start_save(
        self, fn: Callable[[Task], object], on_success: Callable[[object], None]
    ) -> None:
        self._saving = True
        self._update_buttons()
        self.show_message("Saving...")
        self.runner.start(fn, on_success=on_success, on_failure=self._save_failed)

    def _saved_new(self, recording_id: int) -> None:
        self._saving = False
        self._logged_id = recording_id
        self._duplicate_checked = True
        self.show_message(f"Saved as recording {recording_id}.", ItemState.OK)
        self.reload_choices()
        self.refresh_checklist()
        self.saved.emit(recording_id)
        details = ""
        if self._location is not None:
            details = (
                f"\n\nFolder: {self._location.full_path}"
                f"\nArchive state: {self._location.archive_state}"
            )
        QMessageBox.information(
            self, "Recording saved", f"Saved as recording {recording_id}.{details}"
        )

    def _saved_edit(self, recording_id: int | None) -> None:
        self._saving = False
        self.show_message(f"Saved changes to recording {recording_id}.", ItemState.OK)
        if recording_id is not None:
            self.load_recording(
                recording_id, message=self.message_text, message_state=ItemState.OK
            )
            self.saved.emit(recording_id)
        QMessageBox.information(
            self, "Recording saved", f"Saved changes to recording {recording_id}."
        )

    def _clear_message(self) -> None:
        """Drop a message about an earlier folder or save."""
        self.show_message("" if self.config.db_path else NO_DATABASE, ItemState.TODO)

    def _save_failed(self, exc: Exception) -> None:
        self._saving = False
        self.show_message(f"Not saved: {exc}", ItemState.ERROR)
        self.refresh_checklist()

    # =====================================================================
    # Deleting an entry added by mistake (DECISIONS.md D89)
    # =====================================================================

    def _blocked(self, recording_id: int) -> str | None:
        return None if self._deletion_blocked is None else self._deletion_blocked(recording_id)

    def delete_entry(self) -> None:
        """Delete the entry open in edit mode, after a question. Its files stay.

        A worker first reads the entry and its history again (entry.check_deletion());
        the question follows, then a second worker saves the copy and deletes.
        """
        original, db = self._original, self.config.db_path
        if original is None or original.id is None or not db:
            return
        if self._saving or self._scan_task is not None:
            return
        if self._records_folder is None:
            self.show_message(NO_RECORDS_FOLDER, ItemState.ERROR)
            return
        blocked = self._blocked(original.id)
        if blocked is not None:
            self.show_message(blocked, ItemState.ERROR)
            return
        self._saving = True
        self._update_buttons()
        self.show_message("Checking the entry...")
        self.runner.start(
            lambda task: entry.check_deletion(db, original),
            on_success=self._deletion_checked,
            on_failure=self._delete_failed,
        )

    def _deletion_checked(self, check: entry.DeletionCheck) -> None:
        self._saving = False
        self._update_buttons()
        db, folder, rid = self.config.db_path, self._records_folder, check.recording.id
        if not db or folder is None or rid is None or self._original is None:
            return
        question = entry.delete_question(check, self._offset, folder)
        if not confirm_delete(self, question):
            self.show_message("Nothing deleted.", ItemState.INFO)
            return
        blocked = self._blocked(rid)  # the queue may have taken it meanwhile
        if blocked is not None:
            self.show_message(blocked, ItemState.ERROR)
            return
        self._saving = True
        self._update_buttons()
        self.show_message("Deleting...")
        self.runner.start(
            lambda task: entry.delete_entry(
                db, check, records_folder=folder, deleted_by=entry.default_logged_by()
            ),
            on_success=lambda record: self._entry_deleted(rid, record),
            on_failure=self._delete_failed,
        )

    def _entry_deleted(self, recording_id: int, record: Path) -> None:
        self._saving = False
        self.clear_form()
        self.show_message(entry.deleted_text(recording_id, record), ItemState.OK)
        self.deleted.emit(recording_id)

    def _delete_failed(self, exc: Exception) -> None:
        self._saving = False
        self.show_message(f"Not deleted: {exc}", ItemState.ERROR)
        self.refresh_checklist()

    def _channel_like_parent(self) -> str | None:
        """The parent folder when a new entry's folder is named like a channel (D27)."""
        if self._original is not None or self._location is None or self.batch_mode:
            return None
        return entry.channel_like_parent(self._location)

    def _use_parent_folder(self) -> None:
        """Switch to the parent of the chosen folder, as typed (D27)."""
        text = self.folder_edit.text().strip()
        if text:
            self.folder_edit.setText(str(Path(text).parent))

    def _edit_existing(self) -> None:
        if self._logged_id is not None:
            self.load_recording(self._logged_id)

    def load_recording(
        self, recording_id: int, *, message: str = "", message_state: ItemState | None = None
    ) -> None:
        """Open edit mode for a stored recording (DECISIONS.md D16).

        message, with its state, replaces the message line once the entry is open.
        """
        db = self.config.db_path
        if not db:
            self.show_message(NO_DATABASE, ItemState.TODO)
            return
        self.runner.start(
            lambda task: entry.load_recording(db, recording_id),
            on_success=lambda rec: self._enter_edit(rec, message, message_state),
            on_failure=lambda exc: self.show_message(
                f"Cannot open recording {recording_id}: {exc}", ItemState.ERROR
            ),
        )

    def _enter_edit(
        self, rec: Recording, message: str, message_state: ItemState | None = None
    ) -> None:
        self.cancel_scan()
        if self.batch_mode:  # the caller asked about unsaved input first (D45)
            self._set_mode(several=False)
            self._leave_folders()
        self._original = rec
        self._clear_scan()
        form = entry.input_from_recording(rec)
        location = Location(
            storage_root=rec.storage_root, rel_path=rec.rel_path, archive_state=rec.archive_state
        )
        self.folder_edit.blockSignals(True)
        self.folder_edit.setText(location.full_path)
        self.folder_edit.blockSignals(False)
        _set_read_only(self.folder_edit, True)
        self.browse_button.setEnabled(False)
        self._set_location(location, None)
        self._set_duration(form.file_duration_s)
        self._duration_set_by_user = True  # the stored duration stays (D16, D22)
        self._duration_from_names = False
        self.logged_by_edit.setText(form.logged_by)
        self.site_combo.setCurrentIndex(self.site_combo.findData(form.site_id))
        self._select_project(form.project_id)
        self.plan_edit.setText(form.recording_plan_ref)
        self.remarks_edit.setPlainText(form.remarks)
        self.dtype_combo.setCurrentIndex(self.dtype_combo.findData(form.dtype))
        self.layout_combo.setCurrentIndex(self.layout_combo.findData(form.iq_layout))
        self.endian_combo.setCurrentIndex(self.endian_combo.findData(form.endianness))
        self.header_spin.setValue(form.header_bytes)
        self._show_stored_channels(rec)
        self.param_table.set_rows(form.params)
        self.mode_label.setText(f"Editing recording {rec.id}")
        self.show_message(message, message_state)
        self.refresh_checklist()

    # =====================================================================
    # Several folders (DECISIONS.md D90)
    # =====================================================================

    def _set_mode(self, *, several: bool) -> None:
        """Set the mode buttons without the switch they start."""
        for radio in (self.one_radio, self.several_radio):
            radio.blockSignals(True)
        self.several_radio.setChecked(several)
        self.one_radio.setChecked(not several)
        for radio in (self.one_radio, self.several_radio):
            radio.blockSignals(False)

    def _mode_toggled(self, several: bool) -> None:
        if several:
            self._enter_folders()
            return
        unsaved = self.unsaved_folders()
        if unsaved and not self._confirm_drop_folders(unsaved):
            self._set_mode(several=True)
            return
        self._leave_folders()

    def _confirm_drop_folders(self, count: int) -> bool:
        answer = QMessageBox.question(
            self,
            DROP_FOLDERS_TITLE,
            drop_folders_question(count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _enter_folders(self) -> None:
        """Switch to "Several folders". The shared fields stay, as for a new folder (D79)."""
        self.cancel_scan()
        self._clear_scan()
        self.folder_edit.blockSignals(True)
        self.folder_edit.clear()
        self.folder_edit.blockSignals(False)
        self._set_location(None, None)
        self._reset_scan_fields()
        self._carried = {}  # each folder takes band and fc from its own log (D88)
        self._kept = False
        self._clear_folders()
        self.one_page.setVisible(False)
        self.several_page.setVisible(True)
        self.source_box.setTitle("1 · Source folders")
        self.duration_spin.setEnabled(False)
        self.duration_spin.setToolTip("Each folder takes its file duration from its file names.")
        self.folder_label.setVisible(True)
        self.folder_checklist.setVisible(True)
        self._clear_message()
        self.refresh_checklist()

    def _leave_folders(self) -> None:
        """Back to "One folder". The list is dropped; the shared fields stay."""
        self._clear_folders()
        self._reset_scan_fields()
        self._set_location(None, None)
        self.start_edit.clear()
        self.end_edit.clear()
        self.several_page.setVisible(False)
        self.one_page.setVisible(True)
        self.source_box.setTitle("1 · Source folder")
        self.duration_spin.setEnabled(True)
        self.duration_spin.setToolTip("")
        self.folder_label.setVisible(False)
        self.folder_checklist.setVisible(False)
        self.channel_table.setEnabled(True)
        self._show_log_rows(None, self.current_input())
        self._clear_message()
        self.refresh_checklist()

    def _clear_folders(self) -> None:
        self._cancel_batch_task()
        self._folders = []
        self._selected_key = None
        self._views = []
        self._checks.clear()
        self._parent_recording = None
        self.folder_table.set_rows([])
        self.batch_line.clear()
        self.add_parent_button.setVisible(False)
        self.folder_checklist.set_items([])

    def _cancel_batch_task(self) -> None:
        if self._batch_task is not None:
            self._batch_task.cancel()

    def _folder(self, key: int | None) -> batchlog.BatchFolder | None:
        return next((f for f in self._folders if f.key == key), None)

    def add_folders(self, parent: Path | None = None) -> None:
        """Add the recording folders inside `parent`, then scan them. Without `parent`,
        a folder dialog asks. The listing runs in a worker, as the parent may be on
        the NAS."""
        if self._batch_task is not None or self._saving:
            return
        if parent is None:
            chosen = QFileDialog.getExistingDirectory(self, "Folder that holds the recordings")
            if not chosen:
                return
            parent = Path(chosen)
        folder = parent
        self.batch_line.setText(f"Looking for recording folders in {folder}...")
        self._batch_task = self.runner.start(
            lambda task: batchlog.list_candidates(folder),
            on_success=self._candidates_listed,
            on_failure=self._batch_failed,
        )
        self._update_buttons()

    def _candidates_listed(self, found: batchlog.Candidates) -> None:
        self._batch_task = None
        self._parent_recording = None
        self.add_parent_button.setVisible(False)
        added = self._add_paths(found.folders)
        repeated = len(found.folders) - len(added)
        if not found.folders and found.parent_is_recording:
            self._parent_recording = found.parent
            self.batch_line.setText(PARENT_IS_RECORDING)
            self.add_parent_button.setVisible(True)
        elif not found.folders:
            self.batch_line.setText(f"No recording folders found in {found.parent}.")
        else:
            text = f"Added {len(added):,} {'folder' if len(added) == 1 else 'folders'}."
            if repeated:
                text += f" {repeated:,} {'was' if repeated == 1 else 'were'} already in the list."
            self.batch_line.setText(text)
        self._update_buttons()
        if added:
            self.scan_folders([f.key for f in added])
        else:
            self.refresh_checklist()

    def _add_paths(self, paths: Sequence[Path]) -> list[batchlog.BatchFolder]:
        """New list entries for the paths not yet listed."""
        added = []
        for path in paths:
            text = str(path)
            if any(batchlog.same_folder(text, f.path) for f in self._folders):
                continue
            folder = batchlog.BatchFolder(path=text)
            self._folders.append(folder)
            added.append(folder)
        return added

    def _add_parent_as_one(self) -> None:
        parent = self._parent_recording
        self.add_parent_button.setVisible(False)
        self._parent_recording = None
        if parent is None:
            return
        added = self._add_paths([parent])
        self.batch_line.setText(
            f"Added {parent}." if added else f"{parent} is already in the list."
        )
        if added:
            self.scan_folders([added[0].key])

    def remove_folder(self) -> None:
        """Take the selected folder off the list. Nothing is written."""
        if self._batch_task is not None or self._saving or self._selected_key is None:
            return
        self._folders = [f for f in self._folders if f.key != self._selected_key]
        self._selected_key = None
        self._show_selected()
        self.refresh_checklist()

    def scan_folders(self, keys: Sequence[int] | None = None) -> None:
        """Scan the listed folders not yet saved, one after another (D90).

        Each folder's result reaches the list as soon as it is scanned. A rescan drops
        what was typed for that folder's channels.
        """
        if self._batch_task is not None or self._saving:
            return
        todo = [
            f for f in self._folders if not f.saved and (keys is None or f.key in set(keys))
        ]
        if not todo:
            return
        nas_roots, resolve, db = self.config.nas_roots, self._resolve_drive, self.config.db_path
        names = list(self._choices.param_names)

        def work(task: Task) -> int:
            for n, folder in enumerate(todo):
                if task.is_cancelled():
                    break
                task.report((n, len(todo), 0))
                try:
                    done = batchlog.scan_folder(
                        folder,
                        nas_roots=nas_roots,
                        resolve_drive=resolve,
                        db_path=db,
                        known_param_names=names,
                        progress=lambda files, n=n: task.report((n, len(todo), files)),
                        cancelled=task.is_cancelled,
                    )
                except ScanCancelled:
                    break
                task.report(done)
            return len(todo)

        self.batch_line.setText(f"Scanning folder 1 of {len(todo):,}...")
        self._batch_task = self.runner.start(
            work,
            on_success=lambda total: self._folders_scanned(),
            on_failure=self._batch_failed,
            on_progress=self._scan_progress,
        )
        self._update_buttons()

    def _scan_progress(self, value: object) -> None:
        if isinstance(value, batchlog.BatchFolder):
            for position, folder in enumerate(self._folders):
                if folder.key == value.key:
                    # An already logged folder starts unticked; otherwise the tick stays.
                    value.ticked = folder.ticked and value.logged_id is None
                    self._folders[position] = value
            if value.key == self._selected_key:
                self._show_selected()
            self._schedule_refresh()
        elif isinstance(value, tuple):
            n, total, files = value
            self.batch_line.setText(f"Scanning folder {n + 1} of {total:,}: {files:,} files found")

    def _folders_scanned(self) -> None:
        self._batch_task = None
        cancelled = sum(1 for f in self._folders if not f.scanned)
        self._folders.sort(
            key=lambda f: (f.start_unix() is None, f.start_unix() or 0.0, f.name.casefold())
        )
        scanned = sum(1 for f in self._folders if f.scanned and not f.saved)
        text = f"Scanned {scanned:,} {'folder' if scanned == 1 else 'folders'}."
        if cancelled:
            text += f" {cancelled:,} not scanned."
        self.batch_line.setText(text)
        if self._selected_key is None and self._folders:
            self._selected_key = self._folders[0].key
        self._show_selected()
        self.refresh_checklist()

    def _batch_failed(self, exc: Exception) -> None:
        self._batch_task = None
        self.batch_line.setText(f"Cannot read the folder: {exc}")
        self.refresh_checklist()

    def _tick_folder(self, key: int, ticked: bool) -> None:
        folder = self._folder(key)
        if folder is not None and not folder.saved:
            folder.ticked = ticked
            self._schedule_refresh()

    def _select_folder(self, key: object) -> None:
        if not isinstance(key, int) or key == self._selected_key:
            return
        self._sync_selected()
        self._selected_key = key
        self._show_selected()
        self._schedule_refresh()

    def _sync_selected(self) -> None:
        """Keep what the channel rows hold for the selected folder (D90)."""
        folder = self._folder(self._selected_key)
        if folder is None or not folder.scanned or folder.saved or not self._channel_rows:
            return
        rows = {c.channel_index: c for c in self.current_input().channels}
        if folder.scan is not None and set(rows) == {c.channel_index for c in folder.scan.channels}:
            folder.channels = rows

    def _show_selected(self) -> None:
        """Section 2 and the channel rows of the selected folder."""
        folder = self._folder(self._selected_key)
        self.folder_table.select_key(self._selected_key)
        if folder is None or folder.scan is None:
            self._set_channel_rows([], {})
            self._set_location(None, None if folder is None else folder.location_error)
            self.start_edit.clear()
            self.end_edit.clear()
            self.channel_table.setEnabled(True)
            return
        self._set_location(folder.location, folder.location_error)
        self._set_duration(folder.file_duration_s)
        shared = replace(self.current_input(), channels=[])
        form, _values = batchlog.form_for(shared, folder, self._choices.param_names)
        scan = folder.scan
        self._set_channel_rows(
            [
                (c.channel_index, c.sub_path, c.start_unix, c.end_unix, c.n_files)
                for c in scan.channels
            ],
            {c.channel_index: c for c in form.channels},
        )
        starts = [c.start_unix for c in scan.channels if c.start_unix is not None]
        ends = [c.end_unix for c in scan.channels if c.end_unix is not None]
        self.start_edit.setText(time_text(min(starts), self._offset) if starts else "")
        self.end_edit.setText(time_text(max(ends), self._offset) if ends else "")
        self.channel_table.setEnabled(not folder.saved)

    def _refresh_folders(self) -> None:
        """Every folder's checklist, the list's checklist and the folder table (D90)."""
        self._sync_selected()
        shared = replace(self.current_input(), channels=[])
        names = self._choices.param_names
        self._views = [
            (f, self._checks.view(shared, f, self._folders, names)) for f in self._folders
        ]
        self.checklist.set_items(batchlog.combined_items(self._views))
        selected = next(((f, v) for f, v in self._views if f.key == self._selected_key), None)
        if selected is None:
            self.folder_label.setText(NO_FOLDER_SELECTED)
            self.folder_checklist.set_items([])
        else:
            self.folder_label.setText(f"Selected folder: {selected[0].name}")
            self.folder_checklist.set_items(selected[1].items)
        self.folder_table.set_rows([self._folder_row(f, v) for f, v in self._views])
        self._show_field_marks(known=selected is not None and selected[0].scan is not None)
        self._show_log_rows(None if selected is None else selected[0], shared)
        self.kept_note.setVisible(False)
        self.edit_existing_button.setVisible(False)
        self.use_parent_button.setVisible(False)
        self.state_note.setText(
            "" if selected is None else entry.state_note(selected[0].location, None)
        )
        self._update_buttons()

    def _show_log_rows(self, folder: batchlog.BatchFolder | None, shared: EntryInput) -> None:
        """The selected folder's RF chain rows and sample type from its log (O55).

        They are saved with the folder (batchlog.form_for()), but section 5 holds only
        the shared rows. Hidden in "One folder" mode and for a folder without a log.
        """
        shown = (
            None
            if folder is None or not self.batch_mode
            else batchlog.log_shown(shared, folder, self._choices.param_names)
        )
        self.log_rows_box.setVisible(shown is not None)
        table = self.log_rows_table
        table.setRowCount(0)
        if shown is None or folder is None:
            self.log_rows_label.clear()
            self.log_rows_note.clear()
            return
        self.log_rows_label.setText(log_rows_title(folder.name))
        for position, p in enumerate(shown.rows):
            table.insertRow(position)
            scope = "Recording" if p.channel_index is None else f"Ch {p.channel_index}"
            for col, text in enumerate((scope, p.param, p.value, p.unit)):
                cell = _cell(text)
                font = cell.font()
                font.setItalic(True)  # as the other values from the log (D82)
                cell.setFont(font)
                cell.setToolTip(LOG_ROWS_TOOLTIP)
                table.setItem(position, col, cell)
        table.setVisible(bool(shown.rows))
        self.log_rows_label.setVisible(bool(shown.rows))
        note = log_rows_note(shown, shared.dtype)
        self.log_rows_note.setText(note)
        self.log_rows_note.setVisible(bool(note))

    def log_rows(self) -> list[tuple[str, ...]]:
        """The rows of the log table as shown, for tests."""
        table = self.log_rows_table
        return [
            tuple(table.item(r, c).text() for c in range(table.columnCount()))
            for r in range(table.rowCount())
        ]

    def _folder_row(self, folder: batchlog.BatchFolder, view: batchlog.FolderView) -> FolderRow:
        state, state_text = batchlog.folder_state(folder, view.items)
        scan = folder.scan
        channels = view.form.channels
        starts = [] if scan is None else [c.start_unix for c in scan.channels if c.start_unix]
        ends = [] if scan is None else [c.end_unix for c in scan.channels if c.end_unix]
        bands_shown = list(dict.fromkeys(c.band.strip() for c in channels if c.band.strip()))
        fs_shown = list(dict.fromkeys(c.fs_text.strip() for c in channels if c.fs_text.strip()))
        return FolderRow(
            key=folder.key,
            ticked=folder.ticked and not folder.saved,
            can_tick=not folder.saved,
            folder=folder.name,
            folder_tooltip=folder.path,
            start=time_text(min(starts), self._offset) if starts else "",
            end=time_text(max(ends), self._offset) if ends else "",
            channels="" if scan is None else str(len(scan.channels)),
            fc=", ".join(c.fc_mhz.strip() or "?" for c in channels),
            band=", ".join(bands_shown),
            fs=", ".join(fs_shown),
            dtype=str(view.form.dtype) if scan is not None else "",
            files="" if scan is None else f"{sum(c.n_files for c in scan.channels):,}",
            size=""
            if scan is None
            else entry.format_size(sum(c.total_bytes for c in scan.channels)),
            state=state,
            state_text=state_text,
        )

    def _save_folders(self, db: str) -> None:
        """Save every ready folder as its own entry, after a question (D90)."""
        built, failed = batchlog.build_recordings(self._views, self._choices.param_names)
        if not built and not failed:
            self.show_message("Complete or fix the items in the checklist first.", ItemState.TODO)
            return
        site, project = self._names()
        question = batchlog.save_question(
            self._views,
            site=site,
            project=project,
            logged_by=self.logged_by_edit.text().strip(),
            offset_hours=self._offset,
        )
        if not confirm_batch_save(self, question):
            self.show_message("Nothing saved.", ItemState.INFO)
            return
        names = {f.key: f.name for f in self._folders}

        def work(task: Task) -> list[batchlog.SaveOutcome]:
            return batchlog.save_all(db, built, progress=task.report, cancelled=task.is_cancelled)

        self._saving = True
        self._update_buttons()
        self.show_message("Saving...")
        self._batch_task = self.runner.start(
            work,
            on_success=lambda outcomes: self._folders_saved([*failed, *outcomes], names),
            on_failure=self._save_failed_folders,
            on_progress=lambda value: self.show_message(
                f"Saving {value[0] + 1:,} of {value[1]:,}..."
            ),
        )

    def _folders_saved(
        self, outcomes: Sequence[batchlog.SaveOutcome], names: dict[int, str]
    ) -> None:
        self._batch_task = None
        self._saving = False
        for outcome in outcomes:
            folder = self._folder(outcome.key)
            if folder is None:
                continue
            folder.saved_id = outcome.recording_id
            folder.save_error = outcome.error
            if outcome.recording_id is not None:
                folder.ticked = False
        state, text = batchlog.saved_text(outcomes, names)
        self.show_message(text, state)
        self._show_selected()
        self.reload_choices()
        self.refresh_checklist()
        ids = [o.recording_id for o in outcomes if o.recording_id is not None]
        if ids:
            self.saved.emit(ids[-1])  # one refresh of the Viewer

    def _save_failed_folders(self, exc: Exception) -> None:
        self._batch_task = None
        self._saving = False
        self.show_message(f"Not saved: {exc}", ItemState.ERROR)
        self.refresh_checklist()

    # =====================================================================
    # Templates (DECISIONS.md D80)
    # =====================================================================

    def _names(self) -> tuple[str, str]:
        """The chosen site's name ("" for none) and project's name ("" for no project)."""
        site = self.site_combo.currentText() if self.site_combo.currentData() is not None else ""
        project = (
            self.project_combo.currentText()
            if self.project_combo.currentData() is not None
            else ""
        )
        return site, project

    def _carried_for_template(self) -> dict[int, ChannelInput]:
        return self._carried if self._original is None else {}

    def template_field_rows(self) -> list[tuple[templates.TemplateField, str, bool]]:
        """The export dialog's rows: field, text with the current value, ticked or not."""
        form = self.current_input()
        site, project = self._names()
        tpl = templates.template_from_input(
            form,
            templates.TemplateField,
            site_name=site,
            project_name=project,
            carried=self._carried_for_template(),
        )
        filled = templates.filled_fields(form, site, project)
        channels = len(tpl.channels or ())
        rows = len(tpl.rf_chain or ())
        values = {
            templates.TemplateField.LOGGED_BY: form.logged_by.strip() or "empty",
            templates.TemplateField.SITE: site or "none chosen",
            templates.TemplateField.PROJECT: project or NO_PROJECT,
            templates.TemplateField.PLAN: _short(form.recording_plan_ref) or "empty",
            templates.TemplateField.REMARKS: _short(form.remarks) or "empty",
            templates.TemplateField.FORMAT: (
                f"{form.dtype}, {form.iq_layout}, {form.endianness}-endian, "
                f"header {form.header_bytes:,} {'byte' if form.header_bytes == 1 else 'bytes'}"
            ),
            templates.TemplateField.CHANNELS: (
                f"{channels} {'channel' if channels == 1 else 'channels'}"
            ),
            templates.TemplateField.RF_CHAIN: f"{rows} {'row' if rows == 1 else 'rows'}",
        }
        return [
            (f, f"{templates.FIELD_LABELS[f]}: {values[f]}", f in filled)
            for f in templates.TemplateField
        ]

    def export_template(
        self,
        path: Path | None = None,
        fields: set[templates.TemplateField] | None = None,
    ) -> None:
        """Save the chosen fields of the form to a template file.

        Without `fields`, a dialog asks which fields to save. Without `path`, a file
        dialog asks where. Tests pass both.
        """
        if fields is None:
            dialog = TemplateFieldsDialog(self.template_field_rows(), self)
            if dialog.exec() != TemplateFieldsDialog.DialogCode.Accepted:
                return
            fields = dialog.chosen()
        if path is None:
            chosen, _filter = QFileDialog.getSaveFileName(
                self,
                "Export template",
                self._template_folder,
                TEMPLATE_FILTER,
                options=QFileDialog.Option.DontConfirmOverwrite,  # asked below, once
            )
            if not chosen:
                return
            path = Path(chosen)
            if path.suffix.lower() != templates.FILE_SUFFIX:
                path = path.with_name(path.name + templates.FILE_SUFFIX)
            if path.exists() and not self._confirm_replace(path):
                self.show_message("Template not saved.", ItemState.INFO)
                return
        site, project = self._names()
        tpl = templates.template_from_input(
            self.current_input(),
            fields,
            site_name=site,
            project_name=project,
            carried=self._carried_for_template(),
        )
        try:
            templates.write_template(path, tpl)
        except templates.TemplateError as exc:
            self.show_message(f"Template not saved: {exc}", ItemState.ERROR)
            return
        self._template_folder = str(path.parent)
        self.show_message(f"Template saved: {path}", ItemState.OK)

    def _confirm_replace(self, path: Path) -> bool:
        answer = QMessageBox.question(
            self,
            REPLACE_TEMPLATE_TITLE,
            replace_template_question(path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def import_template(self, path: Path | None = None) -> None:
        """Fill in the form from a template file. Fields it does not hold stay."""
        if path is None:
            chosen, _filter = QFileDialog.getOpenFileName(
                self, "Import template", self._template_folder, TEMPLATE_FILTER
            )
            if not chosen:
                return
            path = Path(chosen)
        try:
            tpl = templates.read_template(path)
        except templates.TemplateError as exc:
            self.show_message(f"Template not loaded: {exc}", ItemState.ERROR)
            return
        self._template_folder = str(path.parent)
        if self.batch_mode:
            self._import_template_for_folders(tpl)
            return
        used, note = tpl, ""
        values = self._log_values
        if values is not None and self._original is None:
            form = self.current_input()
            conflicts = recorderlog.template_conflicts(values, form, tpl)
            if conflicts:
                choice = ask_template_conflicts(self, conflicts)
                fields = ", ".join(c.what for c in conflicts)
                if choice is ConflictChoice.CANCEL:
                    self.show_message("Template not loaded.", ItemState.INFO)
                    return
                if choice is ConflictChoice.KEEP_LOG:
                    used = recorderlog.keep_log_values(tpl, values, form)
                    note = f"Kept from the recorder's log: {fields}."
                else:
                    note = f"The template replaced the values from the recorder's log: {fields}."
        applied = templates.apply_template(
            self.current_input(), used, self._choices.sites, self._choices.projects
        )
        self._set_template_fields(used, applied)
        notes = [*applied.notes, note] if note else list(applied.notes)
        state = ItemState.INFO if notes else ItemState.OK  # a name not found, or the log
        self.show_message(templates.applied_text(tpl, notes), state)
        self.refresh_checklist()

    def _import_template_for_folders(self, tpl: templates.LogTemplate) -> None:
        """A template in "Several folders" mode sets the shared fields only (D90).

        Each folder keeps the values its own scan and recorder's log give, so the
        template's band and fc are not used, and there is no question as in D87.
        """
        shared = replace(tpl, channels=None)
        applied = templates.apply_template(
            self.current_input(), shared, self._choices.sites, self._choices.projects
        )
        self._set_template_fields(shared, applied)
        notes = list(applied.notes)
        if tpl.channels is not None:
            notes.append(BATCH_TEMPLATE_CHANNELS_NOTE)
        logs = any(f.recorder is not None and f.recorder.found for f in self._folders)
        if logs and (tpl.sample_type is not None or tpl.rf_chain is not None):
            notes.append(BATCH_TEMPLATE_LOG_NOTE)
        self.show_message(
            templates.applied_text(tpl, notes), ItemState.INFO if notes else ItemState.OK
        )
        self.refresh_checklist()

    def _set_template_fields(self, tpl: templates.LogTemplate, applied: templates.Applied) -> None:
        """Put the fields the template holds into the widgets. The others stay."""
        form = applied.form
        if tpl.logged_by is not None:
            self.logged_by_edit.setText(form.logged_by)
        if tpl.site is not None and form.site_id is not None:
            self.site_combo.setCurrentIndex(self.site_combo.findData(form.site_id))
        if tpl.project is not None:
            self._select_project(form.project_id)
        if tpl.recording_plan_ref is not None:
            self.plan_edit.setText(form.recording_plan_ref)
        if tpl.remarks is not None:
            self.remarks_edit.setPlainText(form.remarks)
        if tpl.sample_type is not None:
            self.dtype_combo.setCurrentIndex(self.dtype_combo.findData(tpl.sample_type))
        if tpl.iq_layout is not None:
            self.layout_combo.setCurrentIndex(self.layout_combo.findData(tpl.iq_layout))
        if tpl.endianness is not None:
            self.endian_combo.setCurrentIndex(self.endian_combo.findData(tpl.endianness))
        if tpl.header_bytes is not None:
            self.header_spin.setValue(tpl.header_bytes)
        if tpl.channels is not None:
            if self._original is None:
                self._carried.update(applied.channels)  # for rows a later scan shows (D79)
            for row in self._channel_rows:
                value = applied.channels.get(row.index)
                if value is not None:
                    if row.fc.text() != value.fc_mhz:
                        row.fc.setText(value.fc_mhz)  # the band may follow it (D88)
                        row.fc_log = False  # the template's value, not the log's (D87)
                        _mark_fc(row)
                    if value.band.strip():  # after the fc, so the template's band wins
                        row.band.setCurrentText(value.band)
                        row.band_auto = False
                        _mark_band(row)
        if tpl.rf_chain is not None:
            self.param_table.set_rows(list(form.params))


# =========================================================================
# Helpers
# =========================================================================


def scan_summary(scan: ScanResult, offset_hours: float = 0.0) -> str:
    """One line about a scan, for example 'Found channel folders 0 and 1 · 20 files · ...'.

    Times are shown at offset_hours from UTC (D24).
    """
    if not scan.channels:
        return "No channel folders and no data files found."
    parts = []
    if scan.channels[0].sub_path:
        indices = [str(c.channel_index) for c in scan.channels]
        joined = (
            indices[0] if len(indices) == 1 else ", ".join(indices[:-1]) + " and " + indices[-1]
        )
        parts.append(f"Found channel folder{'s' if len(indices) > 1 else ''} {joined}")
    else:
        parts.append("Found data files in the recording folder")
    n_files = sum(c.n_files for c in scan.channels)
    parts.append(f"{n_files:,} files")
    parts.append(entry.format_size(sum(c.total_bytes for c in scan.channels)))
    starts = [c.start_unix for c in scan.channels if c.start_unix is not None]
    ends = [c.end_unix for c in scan.channels if c.end_unix is not None]
    if starts and ends:
        first = time_text(min(starts), offset_hours)
        last = time_text(max(ends), offset_hours)
        parts.append(f"{first} to {last} {offset_label(offset_hours)}")
    for c in scan.channels:
        if c.gaps:
            missing = sum(g.missing_seconds for g in c.gaps)
            parts.append(f"ch {c.channel_index} has {entry.missing_text(missing)}")
    return " · ".join(parts)


def _read_only() -> QLineEdit:
    """A line edit the app fills in, with a grey background and a tooltip."""
    edit = QLineEdit()
    _set_read_only(edit, True)
    return edit


def _mix(a: QColor, b: QColor, share_of_b: float) -> QColor:
    """a moved share_of_b of the way toward b."""
    keep = 1 - share_of_b
    return QColor.fromRgbF(
        a.redF() * keep + b.redF() * share_of_b,
        a.greenF() * keep + b.greenF() * share_of_b,
        a.blueF() * keep + b.blueF() * share_of_b,
    )


def field_palette(edit: QLineEdit, read_only: bool) -> QPalette:
    """The palette for a line edit under the current light or dark theme.

    Starts from the application's palette for line edits, so it follows the theme.
    A read-only field moves its background 15 % toward the text colour and its text
    20 % toward the background: still readable, and different from an editable
    field in both themes.
    """
    palette = QApplication.palette(edit)
    if read_only:
        base = palette.color(QPalette.ColorRole.Base)
        text = palette.color(QPalette.ColorRole.Text)
        palette.setColor(QPalette.ColorRole.Base, _mix(base, text, 0.15))
        palette.setColor(QPalette.ColorRole.Text, _mix(text, base, 0.2))
    return palette


def _set_read_only(edit: QLineEdit, read_only: bool) -> None:
    """Make a line edit read-only or editable, with colours to match."""
    edit.setReadOnly(read_only)
    edit.setProperty(READ_ONLY_PROPERTY, read_only)
    edit.setPalette(field_palette(edit, read_only))
    edit.setToolTip(READ_ONLY_TOOLTIP if read_only else "")


def _restyle_fields(root: QWidget) -> None:
    """Apply field colours again after the theme changes."""
    for edit in root.findChildren(QLineEdit):
        read_only = edit.property(READ_ONLY_PROPERTY)
        if read_only is not None:
            edit.setPalette(field_palette(edit, bool(read_only)))


def _restyle_sheets(root: QWidget) -> None:
    """Set each field's style sheet again after the theme changes.

    A widget with a style sheet keeps the palette it had when the sheet was set, so
    an italic or framed field would keep the old theme's background (D95).
    """
    for widget in [*root.findChildren(QLineEdit), *root.findChildren(QComboBox)]:
        sheet = widget.styleSheet()
        if sheet:
            widget.setStyleSheet("")
            widget.setStyleSheet(sheet)


def _enum_combo(enum_type: type[SampleType] | type[IqLayout] | type[Endianness]) -> QComboBox:
    combo = QComboBox()
    for member in enum_type:
        combo.addItem(member.value, member)
    return combo


MARK_PROPERTY = "iqdmMark"  # the field's mark for tests: "todo", "error" or ""


def mark_colour(widget: QWidget, mark: entry.ChecklistItem | None) -> QColor | None:
    """The frame colour of a mark: the information colour (amber) for an empty required
    field, the error colour (red) for a wrong value, or None (D95).

    From the application's palette: a widget with a style sheet keeps its old palette
    after a theme switch until its sheet is set again (_restyle_sheets()).
    """
    if mark is None:
        return None
    state = ItemState.INFO if mark.state is ItemState.TODO else ItemState.ERROR
    return colours_for(QApplication.palette(widget))[state]


def mark_style(
    widget: QWidget, mark: entry.ChecklistItem | None, *, italic: bool = False
) -> str:
    """The style sheet of a text field: italic for a filled-in value, and a frame in
    mark_colour() for a mark (D95). The rules name the type, QLineEdit."""
    rules = ["font-style: italic;"] if italic else []
    colour = mark_colour(widget, mark)
    if colour is not None:
        rules.append(f"border: 2px solid {colour.name()}; border-radius: 3px;")
    return f"QLineEdit {{ {' '.join(rules)} }}" if rules else ""


def _show_mark(
    widget: QLineEdit | QComboBox,
    mark: entry.ChecklistItem | None,
    *,
    italic: bool = False,
    tooltip: str = "",
) -> None:
    """Frame a field that is empty but required, or wrong (D95). A wrong value's
    tooltip gives the reason; otherwise the field keeps `tooltip`.

    A dropdown sits in a MarkFrame, which draws the frame, so the dropdown needs no
    style sheet and keeps the look of the Windows style. A text field gets a style
    sheet, which it may need for italics anyway.
    """
    holder = widget.parentWidget()
    if isinstance(widget, QComboBox) and isinstance(holder, MarkFrame):
        holder.set_colour(mark_colour(widget, mark))
    else:
        widget.setStyleSheet(mark_style(widget, mark, italic=italic))
    widget.setProperty(MARK_PROPERTY, "" if mark is None else str(mark.state))
    error = mark is not None and mark.state is ItemState.ERROR
    widget.setToolTip(mark.text if error and mark is not None else tooltip)


def _mark_fs(row: _ChannelRow) -> None:
    """Italic text and a tooltip on an fs value filled in from the file size (D21) or
    from the recorder's log (D82), and the frame of an empty or wrong fs (D95)."""
    if row.fs_log:
        tooltip = recorderlog.FROM_LOG_TOOLTIP
    else:
        tooltip = FS_FILLED_TOOLTIP if row.fs_auto else FS_TOOLTIP
    _show_mark(row.fs, row.fs_mark, italic=row.fs_auto or row.fs_log, tooltip=tooltip)


def _mark_fc(row: _ChannelRow) -> None:
    """Italic text and a tooltip on an fc value from the recorder's log (D82), and the
    frame of an empty or wrong fc (D95)."""
    tooltip = recorderlog.FROM_LOG_TOOLTIP if row.fc_log else ""
    _show_mark(row.fc, row.fc_mark, italic=row.fc_log, tooltip=tooltip)


def _mark_band(row: _ChannelRow) -> None:
    """Italic text and a tooltip on a band filled in from fc (D88)."""
    row.band.setStyleSheet("font-style: italic;" if row.band_auto else "")
    band = bands.band_named(row.band.currentText()) if row.band_auto else None
    row.band.setToolTip(BAND_TOOLTIP if band is None else band_filled_tooltip(band))


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _short(text: str, limit: int = 40) -> str:
    """The first line of `text`, cut at `limit` characters, for the export dialog."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "\N{HORIZONTAL ELLIPSIS}"
