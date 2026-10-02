"""Log recording tab: scan a recording folder and add it to the database.

SPEC section 6. The logic lives in iqdm.entry, which has no Qt. This module builds
the form, runs scans and database work in a TaskRunner, and shows the checklist.
Edit mode follows DECISIONS.md D16, times are UTC (D17), fc and fs are MHz (D19).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
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
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iqdm import entry
from iqdm.config import Config
from iqdm.db.connection import DatabaseError
from iqdm.entry import ChannelInput, Choices, EntryInput
from iqdm.gui.widgets.checklist import ChecklistView
from iqdm.gui.widgets.param_table import ParamTable
from iqdm.gui.workers import Task, TaskRunner
from iqdm.location import DriveResolver, Location, LocationError, mapped_drive_unc, split_location
from iqdm.models import Endianness, IqLayout, Recording, SampleType
from iqdm.scan.scanner import ScanCancelled, ScanError, ScanResult, scan_recording
from iqdm.timeutil import unix_to_iso

CHANNEL_HEADERS = (
    "Ch",
    "Folder",
    "Band",
    "fc (MHz)",
    "fs (MHz)",
    "Start (UTC)",
    "End (UTC)",
    "Files",
    "Coverage",
)
REFRESH_DELAY_MS = 150  # checklist refresh after typing stops
NO_DATABASE = "No database configured. Set db_path in the configuration file, or start with --db."


def utc_text(t: float | None) -> str:
    """'2026-09-30 02:00:00' for a Unix time, '' for None. Always UTC (D17)."""
    return "" if t is None else unix_to_iso(t).replace("T", " ").removesuffix("Z")


@dataclass(frozen=True, kw_only=True)
class ScanOutcome:
    """Result of the scan task: the scan and the duplicate check."""

    scan: ScanResult
    logged_id: int | None = None
    duplicate_checked: bool = False
    db_error: str | None = None


@dataclass
class _ChannelRow:
    index: int
    band: QComboBox
    fc: QLineEdit
    fs: QLineEdit


class LogTab(QWidget):
    """Form for logging a recording folder, and for editing a logged one."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        resolve_drive: DriveResolver | None = mapped_drive_unc,
        runner: TaskRunner | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = Config() if config is None else config
        self._resolve_drive = resolve_drive
        self.runner = TaskRunner(self) if runner is None else runner

        self._choices = Choices(sites=[], param_names=[], bands=[])
        self._raw_scan: ScanResult | None = None  # at the duration used for the scan
        self._scan: ScanResult | None = None  # at the current duration
        self._location: Location | None = None
        self._location_error: str | None = None
        self._logged_id: int | None = None
        self._duplicate_checked = False
        self._original: Recording | None = None
        self._scan_task: Task | None = None
        self._saving = False
        self._channel_rows: list[_ChannelRow] = []

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
        layout = QVBoxLayout(box)
        layout.addLayout(row)
        layout.addWidget(self.scan_summary)
        return box

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
        self.logged_by_edit.textChanged.connect(self._schedule_refresh)
        self.site_combo = QComboBox()
        self.site_combo.currentIndexChanged.connect(self._schedule_refresh)
        self.add_site_button = QPushButton("Add site")
        self.add_site_button.clicked.connect(self.add_site)
        self.plan_edit = QLineEdit()
        self.storage_root_edit = _read_only()
        self.rel_path_edit = _read_only()
        self.state_edit = _read_only()
        self.remarks_edit = QPlainTextEdit()
        self.remarks_edit.setPlaceholderText("Anything a future reader should know")
        self.remarks_edit.setFixedHeight(60)

        site_row = QHBoxLayout()
        site_row.addWidget(self.site_combo, 1)
        site_row.addWidget(self.add_site_button)

        grid = QGridLayout(box)
        grid.addWidget(QLabel("Start (UTC) · from scan"), 0, 0)
        grid.addWidget(QLabel("End (UTC) · from scan"), 0, 1)
        grid.addWidget(QLabel("File duration"), 0, 2)
        grid.addWidget(QLabel("Logged by"), 0, 3)
        grid.addWidget(self.start_edit, 1, 0)
        grid.addWidget(self.end_edit, 1, 1)
        grid.addWidget(self.duration_spin, 1, 2)
        grid.addWidget(self.logged_by_edit, 1, 3)
        grid.addWidget(QLabel("Site"), 2, 0)
        grid.addWidget(QLabel("Recording plan reference"), 2, 1, 1, 3)
        grid.addLayout(site_row, 3, 0)
        grid.addWidget(self.plan_edit, 3, 1, 1, 3)
        grid.addWidget(QLabel("Storage root · from folder"), 4, 0, 1, 2)
        grid.addWidget(QLabel("Relative path"), 4, 2)
        grid.addWidget(QLabel("Archive state"), 4, 3)
        grid.addWidget(self.storage_root_edit, 5, 0, 1, 2)
        grid.addWidget(self.rel_path_edit, 5, 2)
        grid.addWidget(self.state_edit, 5, 3)
        grid.addWidget(QLabel("Remarks (optional)"), 6, 0, 1, 4)
        grid.addWidget(self.remarks_edit, 7, 0, 1, 4)
        return box

    def _build_format(self) -> QGroupBox:
        box = QGroupBox("3 · File format")
        self.dtype_combo = _enum_combo(SampleType)
        self.layout_combo = _enum_combo(IqLayout)
        self.endian_combo = _enum_combo(Endianness)
        self.header_spin = QSpinBox()
        self.header_spin.setRange(0, 2_000_000_000)
        for widget in (self.dtype_combo, self.layout_combo, self.endian_combo):
            widget.currentIndexChanged.connect(self._schedule_refresh)
        self.header_spin.valueChanged.connect(self._schedule_refresh)

        layout = QFormLayout(box)
        layout.addRow("Sample type", self.dtype_combo)
        layout.addRow("IQ layout", self.layout_combo)
        layout.addRow("Endianness", self.endian_combo)
        layout.addRow("Header bytes", self.header_spin)
        return box

    def _build_channels(self) -> QGroupBox:
        box = QGroupBox("4 · Channels")
        self.channel_table = QTableWidget(0, len(CHANNEL_HEADERS))
        self.channel_table.setHorizontalHeaderLabels(CHANNEL_HEADERS)
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
        return box

    def _build_side_panel(self) -> QGroupBox:
        box = QGroupBox("Before saving")
        self.mode_label = QLabel()
        self.checklist = ChecklistView()
        self.state_note = QLabel()
        self.state_note.setWordWrap(True)
        self.edit_existing_button = QPushButton("Edit existing entry")
        self.edit_existing_button.clicked.connect(self._edit_existing)
        self.save_button = QPushButton("Save entry")
        self.save_button.clicked.connect(self.save)
        self.clear_button = QPushButton("Clear form")
        self.clear_button.clicked.connect(self.clear_form)
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button, 1)
        buttons.addWidget(self.clear_button)
        layout = QVBoxLayout(box)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.checklist, 1)
        layout.addWidget(self.edit_existing_button)
        layout.addWidget(self.state_note)
        layout.addLayout(buttons)
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

    def show_message(self, text: str) -> None:
        self.message_label.setText(text)

    def current_input(self) -> EntryInput:
        return EntryInput(
            logged_by=self.logged_by_edit.text(),
            site_id=self.site_combo.currentData(),
            recording_plan_ref=self.plan_edit.text(),
            remarks=self.remarks_edit.toPlainText(),
            file_duration_s=self.duration_spin.value(),
            dtype=self.dtype_combo.currentData(),
            iq_layout=self.layout_combo.currentData(),
            endianness=self.endian_combo.currentData(),
            header_bytes=self.header_spin.value(),
            channels=[
                ChannelInput(
                    channel_index=r.index,
                    band=r.band.currentText(),
                    fc_mhz=r.fc.text(),
                    fs_mhz=r.fs.text(),
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
        """Back to an empty new entry."""
        self.cancel_scan()
        self._original = None
        self._clear_scan()
        self.folder_edit.setReadOnly(False)
        self.browse_button.setEnabled(True)
        self.folder_edit.blockSignals(True)
        self.folder_edit.clear()
        self.folder_edit.blockSignals(False)
        self._set_location(None, None)
        self.duration_spin.blockSignals(True)
        self.duration_spin.setValue(1.0)
        self.duration_spin.blockSignals(False)
        self.logged_by_edit.setText(entry.default_logged_by())
        self.site_combo.setCurrentIndex(-1)
        self.plan_edit.clear()
        self.remarks_edit.clear()
        self.dtype_combo.setCurrentIndex(self.dtype_combo.findData(SampleType.INT16))
        self.layout_combo.setCurrentIndex(self.layout_combo.findData(IqLayout.INTERLEAVED_IQ))
        self.endian_combo.setCurrentIndex(self.endian_combo.findData(Endianness.LITTLE))
        self.header_spin.setValue(0)
        self._set_channel_rows([], {})
        self.param_table.set_rows([])
        self.mode_label.setText("New entry")
        self.show_message("" if self.config.db_path else NO_DATABASE)
        self.refresh_checklist()

    def _clear_scan(self) -> None:
        self._raw_scan = None
        self._scan = None
        self._logged_id = None
        self._duplicate_checked = False
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

    def _folder_changed(self, text: str) -> None:
        if self._original is not None:
            return
        self.cancel_scan()
        self._clear_scan()
        self._set_channel_rows([], self._inputs_by_index())
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

    def _duration_changed(self, value: float) -> None:
        if self._raw_scan is not None:
            self._scan = entry.with_file_duration(self._raw_scan, value)
            self._show_scan()
        self._schedule_refresh()

    # =====================================================================
    # Channel table
    # =====================================================================

    def _inputs_by_index(self) -> dict[int, ChannelInput]:
        return {c.channel_index: c for c in self.current_input().channels}

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
            band.addItems(self._choices.bands)
            band.setCurrentText(inp.band)
            fc = QLineEdit(inp.fc_mhz)
            fs = QLineEdit(inp.fs_mhz)
            band.currentTextChanged.connect(self._schedule_refresh)
            fc.textChanged.connect(self._schedule_refresh)
            fs.textChanged.connect(self._schedule_refresh)
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
                utc_text(start),
                utc_text(end),
                "" if n_files is None else f"{n_files:,}",
                coverage,
            )
            for col, text in enumerate(cells):
                if text is not None:
                    self.channel_table.setItem(position, col, _cell(text))
            self.channel_table.setCellWidget(position, 2, band)
            self.channel_table.setCellWidget(position, 3, fc)
            self.channel_table.setCellWidget(position, 4, fs)
            self._channel_rows.append(_ChannelRow(index=index, band=band, fc=fc, fs=fs))
        self.param_table.set_channels([r.index for r in self._channel_rows])

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
        starts = [c.start_unix for c in scan.channels if c.start_unix is not None]
        ends = [c.end_unix for c in scan.channels if c.end_unix is not None]
        self.start_edit.setText(utc_text(min(starts)) if starts else "")
        self.end_edit.setText(utc_text(max(ends)) if ends else "")
        self.scan_summary.setText(scan_summary(scan))

    def _show_stored_channels(self, rec: Recording) -> None:
        self._set_channel_rows(
            [
                (c.channel_index, c.sub_path, c.start_unix, c.end_unix, c.n_files)
                for c in rec.channels
            ],
            {c.channel_index: c for c in entry.input_from_recording(rec).channels},
        )
        self.start_edit.setText(utc_text(rec.start_unix))
        self.end_edit.setText(utc_text(rec.end_unix))

    # =====================================================================
    # Checklist
    # =====================================================================

    def _schedule_refresh(self, *_: object) -> None:
        self._refresh_timer.start()

    def refresh_checklist(self) -> None:
        self._refresh_timer.stop()
        items = entry.checklist(
            self.current_input(),
            scan=self._scan,
            location=self._location,
            location_error=self._location_error,
            logged_id=self._logged_id,
            duplicate_checked=self._duplicate_checked,
            original=self._original,
        )
        self.checklist.set_items(items)
        self.state_note.setText(entry.state_note(self._location, self._original))
        self.edit_existing_button.setVisible(self._original is None and self._logged_id is not None)
        self._update_buttons()

    def _update_buttons(self) -> None:
        scanning = self._scan_task is not None
        self.scan_button.setEnabled(not scanning and not self._saving)
        self.cancel_button.setEnabled(scanning)
        self.save_button.setEnabled(
            bool(self.config.db_path)
            and not scanning
            and not self._saving
            and entry.can_save(self.checklist.items)
        )

    # =====================================================================
    # Database lists
    # =====================================================================

    def reload_choices(self, select_site: int | None = None) -> None:
        """Load sites, parameter names and bands in a worker."""
        db = self.config.db_path
        if not db:
            return
        keep = self.site_combo.currentData() if select_site is None else select_site
        self.runner.start(
            lambda task: entry.load_choices(db),
            on_success=lambda result: self._choices_loaded(result, keep),
            on_failure=lambda exc: self.show_message(f"Cannot read the database: {exc}"),
        )

    def _choices_loaded(self, choices: Choices, select_site: int | None) -> None:
        self._choices = choices
        self.site_combo.blockSignals(True)
        self.site_combo.clear()
        for site in choices.sites:
            self.site_combo.addItem(site.name, site.id)
        self.site_combo.setCurrentIndex(self.site_combo.findData(select_site))
        self.site_combo.blockSignals(False)
        self.param_table.set_param_names(choices.param_names)
        for row in self._channel_rows:
            text = row.band.currentText()
            row.band.blockSignals(True)
            row.band.clear()
            row.band.addItems(choices.bands)
            row.band.setCurrentText(text)
            row.band.blockSignals(False)
        self.refresh_checklist()

    def add_site(self) -> None:
        db = self.config.db_path
        if not db:
            self.show_message(NO_DATABASE)
            return
        name, ok = QInputDialog.getText(self, "Add site", "Site name:")
        if not ok or not name.strip():
            return
        self.runner.start(
            lambda task: entry.add_site(db, name),
            on_success=lambda site: self._site_added(site),
            on_failure=lambda exc: self.show_message(f"Site not added: {exc}"),
        )

    def _site_added(self, site: object) -> None:
        site_id = getattr(site, "id", None)
        self.show_message(f"Added site {getattr(site, 'name', '')}.")
        self.reload_choices(select_site=site_id)

    # =====================================================================
    # Scanning
    # =====================================================================

    def start_scan(self) -> None:
        if self._scan_task is not None or self._saving:
            return
        folder = self.folder_edit.text().strip()
        if not folder:
            self.show_message("Choose a folder first.")
            return
        if self._original is None and self._location is None:
            self.show_message(f"Folder cannot be logged: {self._location_error}")
            return
        duration = self.duration_spin.value()
        db = self.config.db_path
        location = self._location if self._original is None else None

        def work(task: Task) -> ScanOutcome:
            scan = scan_recording(
                Path(folder), duration, progress=task.report, cancelled=task.is_cancelled
            )
            if location is None or not db:
                return ScanOutcome(scan=scan)
            try:
                logged = entry.find_logged(db, location)
            except (DatabaseError, OSError) as exc:
                return ScanOutcome(scan=scan, db_error=str(exc))
            return ScanOutcome(scan=scan, logged_id=logged, duplicate_checked=True)

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
        self._scan = entry.with_file_duration(outcome.scan, self.duration_spin.value())
        self._logged_id = outcome.logged_id
        self._duplicate_checked = outcome.duplicate_checked
        self._show_scan()
        if outcome.db_error is not None:
            self.show_message(f"Cannot check the database for this folder: {outcome.db_error}")
        self.refresh_checklist()

    def _scan_failed(self, exc: Exception) -> None:
        self._scan_task = None
        self._clear_scan()
        if self._original is not None:
            self._show_stored_channels(self._original)
        if isinstance(exc, ScanCancelled):
            self.scan_summary.setText("Scan cancelled.")
        elif isinstance(exc, ScanError):
            self.scan_summary.setText("Scan stopped:\n" + "\n".join(exc.problems))
        else:
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
        if not entry.can_save(self.checklist.items):
            self.show_message("Fix the items marked in the checklist first.")
            return
        try:
            rec = entry.build_recording(
                self.current_input(),
                scan=self._scan,
                location=self._location,
                original=self._original,
            )
        except ValueError as exc:
            self.show_message(f"Not saved: {exc}")
            return

        original = self._original
        if original is None:
            self._start_save(lambda task: entry.save_new(db, rec), self._saved_new)
            return
        allow_removal = False
        if self._scan is not None:
            removed = entry.channel_set_change(original, self._scan).removed
            if removed:
                if not self._confirm_removal(original, removed):
                    self.show_message("Nothing saved. The channels stay in the database.")
                    return
                allow_removal = True
        self._start_save(
            lambda task: entry.save_edit(db, rec, allow_channel_removal=allow_removal),
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
        self.show_message(f"Saved as recording {recording_id}.")
        self.reload_choices()
        self.refresh_checklist()

    def _saved_edit(self, recording_id: int | None) -> None:
        self._saving = False
        self.show_message(f"Saved changes to recording {recording_id}.")
        if recording_id is not None:
            self.load_recording(recording_id, message=self.message_label.text())

    def _save_failed(self, exc: Exception) -> None:
        self._saving = False
        self.show_message(f"Not saved: {exc}")
        self.refresh_checklist()

    def _edit_existing(self) -> None:
        if self._logged_id is not None:
            self.load_recording(self._logged_id)

    def load_recording(self, recording_id: int, *, message: str = "") -> None:
        """Open edit mode for a stored recording (DECISIONS.md D16)."""
        db = self.config.db_path
        if not db:
            self.show_message(NO_DATABASE)
            return
        self.runner.start(
            lambda task: entry.load_recording(db, recording_id),
            on_success=lambda rec: self._enter_edit(rec, message),
            on_failure=lambda exc: self.show_message(
                f"Cannot open recording {recording_id}: {exc}"
            ),
        )

    def _enter_edit(self, rec: Recording, message: str) -> None:
        self.cancel_scan()
        self._original = rec
        self._clear_scan()
        form = entry.input_from_recording(rec)
        location = Location(
            storage_root=rec.storage_root, rel_path=rec.rel_path, archive_state=rec.archive_state
        )
        self.folder_edit.blockSignals(True)
        self.folder_edit.setText(location.full_path)
        self.folder_edit.blockSignals(False)
        self.folder_edit.setReadOnly(True)
        self.browse_button.setEnabled(False)
        self._set_location(location, None)
        self.duration_spin.blockSignals(True)
        self.duration_spin.setValue(form.file_duration_s)
        self.duration_spin.blockSignals(False)
        self.logged_by_edit.setText(form.logged_by)
        self.site_combo.setCurrentIndex(self.site_combo.findData(form.site_id))
        self.plan_edit.setText(form.recording_plan_ref)
        self.remarks_edit.setPlainText(form.remarks)
        self.dtype_combo.setCurrentIndex(self.dtype_combo.findData(form.dtype))
        self.layout_combo.setCurrentIndex(self.layout_combo.findData(form.iq_layout))
        self.endian_combo.setCurrentIndex(self.endian_combo.findData(form.endianness))
        self.header_spin.setValue(form.header_bytes)
        self._show_stored_channels(rec)
        self.param_table.set_rows(form.params)
        self.mode_label.setText(f"Editing recording {rec.id}")
        self.show_message(message)
        self.refresh_checklist()


# =========================================================================
# Helpers
# =========================================================================


def scan_summary(scan: ScanResult) -> str:
    """One line about a scan, for example 'Found channel folders 0 and 1 · 20 files · ...'."""
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
        parts.append(f"{utc_text(min(starts))} to {utc_text(max(ends))} UTC")
    for c in scan.channels:
        if c.gaps:
            missing = sum(g.missing_seconds for g in c.gaps)
            parts.append(f"ch {c.channel_index} has {entry.missing_text(missing)}")
    return " · ".join(parts)


def _read_only() -> QLineEdit:
    edit = QLineEdit()
    edit.setReadOnly(True)
    return edit


def _enum_combo(enum_type: type[SampleType] | type[IqLayout] | type[Endianness]) -> QComboBox:
    combo = QComboBox()
    for member in enum_type:
        combo.addItem(member.value, member)
    return combo


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item
