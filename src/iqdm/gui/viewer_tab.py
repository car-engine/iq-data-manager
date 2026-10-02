"""Viewer tab: browse and filter recordings, their channels and RF chain details.

SPEC section 5. The logic lives in iqdm.viewer, which has no Qt. This module builds
the tab, runs database reads and gap scans in a TaskRunner, and shows the results.
The Viewer only reads: every connection is read-only, and Refresh queries again.
Times are shown and filtered at the configured offset from UTC (D24, D43). Coverage
below the configured threshold is amber with a mark (D39).
"""

import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QItemSelection,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iqdm import viewer
from iqdm.config import Config
from iqdm.entry import ItemState, format_frequency, format_mhz
from iqdm.gui.log_tab import NO_DATABASE
from iqdm.gui.widgets.checklist import MARKS, colours_for
from iqdm.gui.widgets.recording_model import (
    ID_ROLE,
    RecordingTableModel,
    low_coverage_tooltip,
)
from iqdm.gui.widgets.timeline import TimelineView
from iqdm.gui.workers import Task, TaskRunner
from iqdm.models import ArchiveState, Channel, RecordingFilter, channel_coverage
from iqdm.scan.scanner import ScanCancelled, ScanError, ScanResult, scan_recording
from iqdm.timeutil import display_time, offset_label

FOLDER_NOT_OPENED = "Cannot open the folder. Check that it exists and the network connection."
SCAN_HINT = "Scan the recording folder to see where data is missing."
SELECT_HINT = "Select a recording to see its channels."
DETAILS_HINT = "Select a recording or a channel for details."


def channel_headers(zone: str) -> tuple[str, ...]:
    return ("Ch", "Band", "fc (MHz)", "fs", f"Start ({zone})", f"End ({zone})", "Files", "Coverage")


def _open_in_explorer(folder: Path) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def _cell(text: str, tooltip: str = "", colour: QColor | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if tooltip:
        item.setToolTip(tooltip)
    if colour is not None:
        item.setForeground(colour)
    return item


def _read_only_table(headers: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.setWordWrap(False)
    return table


def _fit_height(table: QTableWidget) -> None:
    """Make a short table as tall as its rows, so the details panel has no empty boxes."""
    height = table.horizontalHeader().height() + 2 * table.frameWidth()
    height += sum(table.rowHeight(r) for r in range(table.rowCount()))
    table.setFixedHeight(height + 2)


class ViewerTab(QWidget):
    """Filters, the recordings list, channels, gap scan and details. Read-only."""

    edit_requested = Signal(int)  # recording id for the Log tab's edit mode (D16)

    def __init__(
        self,
        config: Config | None = None,
        *,
        runner: TaskRunner | None = None,
        open_folder: Callable[[Path], bool] = _open_in_explorer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = Config() if config is None else config
        self._offset = self.config.display_utc_offset_hours
        self._threshold = self.config.coverage_highlight_percent
        self._open_folder = open_folder
        self.runner = TaskRunner(self) if runner is None else runner

        self._filter: RecordingFilter | None = None
        self._list_id = 0
        self._choices_id = 0
        self._details_id = 0
        self._scan_id = 0
        self._selected_id: int | None = None  # kept across a Refresh
        self._details: viewer.Details | None = None
        self._channel_index: int | None = None
        self._scan: ScanResult | None = None
        self._scan_task: Task | None = None
        self._message: tuple[ItemState, str, str] | None = None  # state, text, tooltip
        self._scan_note: tuple[ItemState, str] | None = None
        self._filter_errors: tuple[str, ...] = ()

        self._build()
        self._clear_details()
        self.refresh()

    # =====================================================================
    # Layout
    # =====================================================================

    def _build(self) -> None:
        self.model = RecordingTableModel(self._offset, self._threshold)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_list())
        bottom = QWidget()
        bottom_row = QHBoxLayout(bottom)
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.addWidget(self._build_channels(), 3)
        bottom_row.addWidget(self._build_details(), 2)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._build_filters())
        layout.addWidget(splitter, 1)

    def _build_filters(self) -> QGroupBox:
        box = QGroupBox("Filters")
        box.setFixedWidth(250)
        self.start_from_edit = QLineEdit()
        self.start_from_edit.setPlaceholderText("YYYY-MM-DD")
        self.start_to_edit = QLineEdit()
        self.start_to_edit.setPlaceholderText("YYYY-MM-DD")
        self.start_from_label = QLabel()
        self.start_to_label = QLabel()
        self.site_combo = QComboBox()
        self.band_combo = QComboBox()
        self.fc_min_edit = QLineEdit()
        self.fc_min_edit.setPlaceholderText("min")
        self.fc_max_edit = QLineEdit()
        self.fc_max_edit.setPlaceholderText("max")
        self.state_combo = QComboBox()
        self.state_combo.addItem("All", None)
        for state in ArchiveState:
            self.state_combo.addItem(str(state), state)
        self.rf_edit = QLineEdit()
        self.rf_edit.setToolTip("Matches a part of a parameter name, value or unit.")
        self.remarks_edit = QLineEdit()
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_filters)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_filters)
        self.filter_error = QLabel()
        self.filter_error.setWordWrap(True)
        self.filter_error.setVisible(False)
        for edit in (
            self.start_from_edit,
            self.start_to_edit,
            self.fc_min_edit,
            self.fc_max_edit,
            self.rf_edit,
            self.remarks_edit,
        ):
            edit.returnPressed.connect(self.apply_filters)
        self._label_times()
        self._fill_choices(viewer.ViewerChoices(sites=[], bands=[]))

        fc_row = QHBoxLayout()
        fc_row.addWidget(self.fc_min_edit)
        fc_row.addWidget(QLabel("to"))
        fc_row.addWidget(self.fc_max_edit)
        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.clear_button)

        layout = QVBoxLayout(box)
        for label, field in (
            (self.start_from_label, self.start_from_edit),
            (self.start_to_label, self.start_to_edit),
            (QLabel("Site"), self.site_combo),
            (QLabel("Band"), self.band_combo),
        ):
            layout.addWidget(label)
            layout.addWidget(field)
        layout.addWidget(QLabel("Centre frequency (MHz)"))
        layout.addLayout(fc_row)
        for label, field in (
            (QLabel("Archive state"), self.state_combo),
            (QLabel("RF chain contains"), self.rf_edit),
            (QLabel("Remarks contain"), self.remarks_edit),
        ):
            layout.addWidget(label)
            layout.addWidget(field)
        layout.addLayout(buttons)
        layout.addWidget(self.filter_error)
        layout.addStretch(1)
        return box

    def _build_list(self) -> QWidget:
        self.count_label = QLabel()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.open_button = QPushButton("Open folder")
        self.open_button.setToolTip("Open the recording folder in Explorer.")
        self.open_button.clicked.connect(self.open_folder)
        self.edit_button = QPushButton("Edit entry")
        self.edit_button.setToolTip("Open this recording in the Log recording tab to change it.")
        self.edit_button.clicked.connect(self.request_edit)
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setResizeContentsPrecision(200)  # rows sampled per column
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.SortOrder.DescendingOrder)  # newest first
        self.table.selectionModel().selectionChanged.connect(self._recording_selected)

        title = QLabel("Recordings")
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addWidget(self.count_label, 1)
        header.addWidget(self.refresh_button)
        header.addWidget(self.open_button)
        header.addWidget(self.edit_button)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.message_label)
        layout.addWidget(self.table, 1)
        return widget

    def _build_channels(self) -> QGroupBox:
        self.channels_box = QGroupBox("Channels")
        self.channel_table = _read_only_table(channel_headers(offset_label(self._offset)))
        self.channel_table.itemSelectionChanged.connect(self._channel_selected)
        self.channel_hint = QLabel(SELECT_HINT)
        self.scan_button = QPushButton("Scan for gaps")
        self.scan_button.setToolTip(
            "Read the file names in the recording folder. Nothing is changed."
        )
        self.scan_button.clicked.connect(self.start_scan)
        self.cancel_scan_button = QPushButton("Cancel")
        self.cancel_scan_button.clicked.connect(self.cancel_scan)
        self.scan_status = QLabel()
        self.scan_status.setWordWrap(True)
        self.timeline = TimelineView()
        self.gap_label = QLabel()
        self.gap_label.setWordWrap(True)
        self.gap_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.difference_label = QLabel()
        self.difference_label.setWordWrap(True)

        scan_row = QHBoxLayout()
        scan_row.addWidget(self.scan_button)
        scan_row.addWidget(self.cancel_scan_button)
        scan_row.addWidget(self.scan_status, 1)
        layout = QVBoxLayout(self.channels_box)
        layout.addWidget(self.channel_hint)
        layout.addWidget(self.channel_table, 1)
        layout.addLayout(scan_row)
        layout.addWidget(self.timeline)
        layout.addWidget(self.gap_label)
        layout.addWidget(self.difference_label)
        return self.channels_box

    def _build_details(self) -> QGroupBox:
        box = QGroupBox("Details")
        self.details_title = QLabel()
        font = self.details_title.font()
        font.setBold(True)
        self.details_title.setFont(font)
        self.details_title.setWordWrap(True)
        self.not_verified_label = QLabel()
        self.not_verified_label.setWordWrap(True)
        self.param_table = _read_only_table(("Applies to", "Parameter", "Value", "Note"))
        self.param_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.param_hint = QLabel("No RF chain details were logged.")
        self.path_label = QLabel()
        self.format_label = QLabel()
        self.plan_label = QLabel()
        self.remarks_label = QLabel()
        self.logged_label = QLabel()
        for label in (
            self.path_label,
            self.format_label,
            self.plan_label,
            self.remarks_label,
            self.logged_label,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.transfer_table = _read_only_table(("When", "Operation", "Scope", "Result", "By"))
        self.transfer_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.transfer_hint = QLabel()

        form = QFormLayout()
        form.addRow("Path", self.path_label)
        form.addRow("Format", self.format_label)
        form.addRow("Plan", self.plan_label)
        form.addRow("Remarks", self.remarks_label)
        form.addRow("Logged", self.logged_label)

        inner = QWidget()
        column = QVBoxLayout(inner)
        column.addWidget(self.details_title)
        column.addWidget(self.not_verified_label)
        column.addWidget(QLabel("RF chain"))
        column.addWidget(self.param_hint)
        column.addWidget(self.param_table)
        column.addLayout(form)
        column.addWidget(QLabel("Transfer history"))
        column.addWidget(self.transfer_hint)
        column.addWidget(self.transfer_table)
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        return box

    def _label_times(self) -> None:
        zone = offset_label(self._offset)
        self.start_from_label.setText(f"Start date from ({zone})")
        self.start_to_label.setText(f"Start date to ({zone})")

    # =====================================================================
    # State
    # =====================================================================

    @property
    def selected_id(self) -> int | None:
        return self._selected_id

    @property
    def details(self) -> viewer.Details | None:
        return self._details

    @property
    def scan(self) -> ScanResult | None:
        return self._scan

    @property
    def active_filter(self) -> RecordingFilter | None:
        return self._filter

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802  (Qt override)
        """Pick the colour set again after a switch between light and dark."""
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        ) and hasattr(self, "model"):
            self._recolour()
        super().changeEvent(event)

    def _colours(self) -> dict[ItemState, QColor]:
        return colours_for(self.palette())

    def _recolour(self) -> None:
        self.model.set_colours(self._colours())
        self._show_message()
        self._show_filter_errors(self._filter_errors)
        self._show_channels()
        self._show_details()
        self._show_scan()

    def apply_config(self, config: Config) -> None:
        """Take a new configuration without a restart (D33). The Viewer holds no input."""
        old = self.config
        self.config = config
        if config.display_utc_offset_hours != self._offset:
            self._offset = config.display_utc_offset_hours
            self._label_times()
            self.model.set_offset(self._offset)
            self.channel_table.setHorizontalHeaderLabels(
                channel_headers(offset_label(self._offset))
            )
            self.timeline.set_offset(self._offset)
            self._show_channels()
            self._show_details()
            self._show_scan()
        if config.coverage_highlight_percent != self._threshold:
            self._threshold = config.coverage_highlight_percent
            self.model.set_threshold(self._threshold)
            self._show_channels()
        if config.db_path != old.db_path:
            self._selected_id = None
            self.model.set_rows([])
            self._clear_details()
            self.refresh()

    # =====================================================================
    # Loading
    # =====================================================================

    def refresh(self) -> None:
        """Query the database again with the applied filter. The selection is kept."""
        db = self.config.db_path
        if not db:
            self._list_id += 1
            self.model.set_rows([])
            self._clear_details()
            self.count_label.setText("")
            self._set_message(ItemState.TODO, NO_DATABASE, "")
            self._update_buttons()
            return
        self._load_choices(db)
        self._load_list(db)

    def _load_choices(self, db: str) -> None:
        self._choices_id += 1
        choices_id = self._choices_id
        self.runner.start(
            lambda task: viewer.load_choices(db),
            on_success=lambda result: self._choices_loaded(choices_id, result),
        )

    def _choices_loaded(self, choices_id: int, choices: object) -> None:
        if choices_id == self._choices_id and isinstance(choices, viewer.ViewerChoices):
            self._fill_choices(choices)

    def _fill_choices(self, choices: viewer.ViewerChoices) -> None:
        site = self.site_combo.currentData()
        band = self.band_combo.currentData()
        self.site_combo.clear()
        self.site_combo.addItem("All sites", None)
        for s in choices.sites:
            self.site_combo.addItem(s.name, s.id)
        self.site_combo.setCurrentIndex(max(0, self.site_combo.findData(site)))
        self.band_combo.clear()
        self.band_combo.addItem("All bands", None)
        for b in choices.bands:
            self.band_combo.addItem(b, b)
        self.band_combo.setCurrentIndex(max(0, self.band_combo.findData(band)))

    def _load_list(self, db: str) -> None:
        self._list_id += 1
        list_id = self._list_id
        flt = self._filter
        self.count_label.setText("Loading\N{HORIZONTAL ELLIPSIS}")
        self.runner.start(
            lambda task: viewer.load_list(db, flt),
            on_success=lambda result: self._list_loaded(list_id, result),
            on_failure=lambda exc: self._list_failed(list_id, exc),
        )

    def _list_loaded(self, list_id: int, result: object) -> None:
        if list_id != self._list_id or not isinstance(result, viewer.ListResult):
            return  # a later load replaces this one
        keep = self._selected_id
        self.model.set_rows(result.summaries)
        self.table.resizeColumnsToContents()  # samples 200 rows per column (see _build_list)
        refreshed = display_time(time.time(), self._offset)[11:16]
        self.count_label.setText(
            f"{len(result.summaries):,} shown \N{MIDDLE DOT} refreshed {refreshed} "
            f"({offset_label(self._offset)})"
        )
        if result.newer_database:
            self._set_message(ItemState.INFO, viewer.NEWER_DATABASE, "")
        else:
            self._set_message(ItemState.OK, "", "")
        row = None if keep is None else self.model.row_of(keep)
        if row is None:
            self._selected_id = None
            self._clear_details()
        else:
            self.select_recording(keep)
        self._update_buttons()

    def _list_failed(self, list_id: int, exc: Exception) -> None:
        if list_id != self._list_id:
            return
        self.model.set_rows([])
        self._selected_id = None
        self._clear_details()
        self.count_label.setText("")
        self._set_message(ItemState.ERROR, viewer.error_text(exc), str(exc))
        self._update_buttons()

    def _set_message(self, state: ItemState, text: str, tooltip: str) -> None:
        self._message = (state, text, tooltip) if text else None
        self._show_message()

    def _show_message(self) -> None:
        if self._message is None:
            self.message_label.setText("")
            self.message_label.setVisible(False)
            return
        state, text, tooltip = self._message
        self.message_label.setText(f"{MARKS[state]}  {text}")
        self.message_label.setToolTip(tooltip)
        self.message_label.setStyleSheet(f"color: {self._colours()[state].name()};")
        self.message_label.setVisible(True)

    @property
    def message(self) -> tuple[ItemState, str, str] | None:
        """The line above the list: state, text and tooltip. None when there is none."""
        return self._message

    # =====================================================================
    # Filters
    # =====================================================================

    def filter_input(self) -> viewer.FilterInput:
        return viewer.FilterInput(
            start_from=self.start_from_edit.text(),
            start_to=self.start_to_edit.text(),
            site_id=self.site_combo.currentData(),
            band=self.band_combo.currentData() or "",
            fc_min=self.fc_min_edit.text(),
            fc_max=self.fc_max_edit.text(),
            archive_state=self.state_combo.currentData(),
            rf_chain_text=self.rf_edit.text(),
            remarks_text=self.remarks_edit.text(),
        )

    def apply_filters(self) -> None:
        result = viewer.parse_filter(self.filter_input(), self._offset)
        self._show_filter_errors(result.errors)
        if result.flt is None:
            return
        self._filter = None if result.flt == RecordingFilter() else result.flt
        self.refresh()

    def clear_filters(self) -> None:
        for edit in (
            self.start_from_edit,
            self.start_to_edit,
            self.fc_min_edit,
            self.fc_max_edit,
            self.rf_edit,
            self.remarks_edit,
        ):
            edit.clear()
        for combo in (self.site_combo, self.band_combo, self.state_combo):
            combo.setCurrentIndex(0)
        self._show_filter_errors(())
        self._filter = None
        self.refresh()

    def _show_filter_errors(self, errors: tuple[str, ...]) -> None:
        self._filter_errors = errors
        mark = MARKS[ItemState.ERROR]
        self.filter_error.setText("\n".join(f"{mark} {e}" for e in errors))
        self.filter_error.setStyleSheet(f"color: {self._colours()[ItemState.ERROR].name()};")
        self.filter_error.setVisible(bool(errors))

    # =====================================================================
    # Selection and details
    # =====================================================================

    def select_recording(self, recording_id: int) -> bool:
        """Select a recording in the list. False if the list does not show it."""
        row = self.model.row_of(recording_id)
        if row is None:
            return False
        self.table.selectRow(row)
        self.table.scrollTo(self.model.index(row, 0))
        self._selected_id = recording_id
        self._load_details(recording_id)  # also after a Refresh of the same recording
        return True

    def _recording_selected(self, selected: QItemSelection, _deselected: QItemSelection) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        recording_id = self.model.data(rows[0], ID_ROLE)
        if isinstance(recording_id, int) and recording_id != self._selected_id:
            self._selected_id = recording_id
            self._load_details(recording_id)
        self._update_buttons()

    def _load_details(self, recording_id: int) -> None:
        db = self.config.db_path
        if not db:
            return
        self._details_id += 1
        details_id = self._details_id
        if self._details is None or self._details.recording.id != recording_id:
            self._clear_details()
            self.channel_hint.setText("Loading\N{HORIZONTAL ELLIPSIS}")
        self.runner.start(
            lambda task: viewer.load_details(db, recording_id),
            on_success=lambda result: self._details_loaded(details_id, result),
            on_failure=lambda exc: self._details_failed(details_id, exc),
        )

    def _details_loaded(self, details_id: int, result: object) -> None:
        if details_id != self._details_id or not isinstance(result, viewer.Details):
            return
        same = self._details is not None and self._details.recording.id == result.recording.id
        self._details = result
        if not same:
            self._channel_index = None
            self._reset_scan()
        self.channel_hint.setText("")
        self.channel_hint.setVisible(False)
        self._show_channels()
        self._show_details()
        self._update_buttons()

    def _details_failed(self, details_id: int, exc: Exception) -> None:
        if details_id != self._details_id:
            return
        self._clear_details()
        self.channel_hint.setText(viewer.error_text(exc))
        self.channel_hint.setToolTip(str(exc))

    def _clear_details(self) -> None:
        self.cancel_scan()
        self._details = None
        self._channel_index = None
        self._reset_scan()
        self.channel_hint.setText(SELECT_HINT)
        self.channel_hint.setToolTip("")
        self.channel_hint.setVisible(True)
        self._show_channels()
        self._show_details()
        self._update_buttons()

    def _show_channels(self) -> None:
        table = self.channel_table
        table.blockSignals(True)
        table.setRowCount(0)
        details = self._details
        if details is None:
            self.channels_box.setTitle("Channels")
            table.blockSignals(False)
            return
        rec = details.recording
        self.channels_box.setTitle(f"Channels \N{MIDDLE DOT} recording {rec.id}")
        colours = self._colours()
        for row, ch in enumerate(rec.channels):
            table.insertRow(row)
            coverage = channel_coverage(ch, rec.file_duration_s)
            low = viewer.coverage_is_low(coverage, self._threshold)
            coverage_text = viewer.coverage_text(coverage)
            if low:
                coverage_text = f"{MARKS[ItemState.INFO]} {coverage_text}"
            values = (
                _cell(str(ch.channel_index)),
                _cell(ch.band or ""),
                _cell(format_mhz(ch.fc_hz)),
                _cell(format_frequency(ch.fs_hz)),
                _cell(display_time(ch.start_unix, self._offset)),
                _cell(display_time(ch.end_unix, self._offset)),
                _cell("" if ch.n_files is None else f"{ch.n_files:,}"),
                _cell(
                    coverage_text,
                    low_coverage_tooltip(self._threshold) if low else "",
                    colours[ItemState.INFO] if low else None,
                ),
            )
            for col, item in enumerate(values):
                table.setItem(row, col, item)
            if ch.channel_index == self._channel_index:
                table.selectRow(row)
        table.blockSignals(False)

    def _channel_selected(self) -> None:
        details = self._details
        rows = self.channel_table.selectionModel().selectedRows()
        if details is None or not rows:
            self._channel_index = None
        else:
            self._channel_index = details.recording.channels[rows[0].row()].channel_index
        self._show_details()

    def _selected_channel(self) -> Channel | None:
        if self._details is None or self._channel_index is None:
            return None
        for ch in self._details.recording.channels:
            if ch.channel_index == self._channel_index:
                return ch
        return None

    def _show_details(self) -> None:
        details = self._details
        self.param_table.setRowCount(0)
        self.transfer_table.setRowCount(0)
        if details is None:
            self.details_title.setText(DETAILS_HINT)
            for label in (
                self.path_label,
                self.format_label,
                self.plan_label,
                self.remarks_label,
                self.logged_label,
                self.transfer_hint,
            ):
                label.setText("")
            self.not_verified_label.setVisible(False)
            for widget in (self.param_table, self.param_hint, self.transfer_table):
                widget.setVisible(False)
            return
        rec = details.recording
        channel = self._selected_channel()
        if channel is None:
            self.details_title.setText(f"Recording {rec.id} \N{MIDDLE DOT} {details.site_name}")
            self.path_label.setText(viewer.recording_path(rec))
        else:
            self.details_title.setText(
                f"Recording {rec.id} \N{MIDDLE DOT} channel {channel.channel_index} "
                f"\N{MIDDLE DOT} {format_mhz(channel.fc_hz)} MHz"
            )
            self.path_label.setText(viewer.channel_path(rec, channel))
        colours = self._colours()
        unverified = viewer.is_unverified(rec, details.transfers)
        self.not_verified_label.setText(
            f"{MARKS[ItemState.INFO]}  Not verified. {viewer.NOT_VERIFIED_NOTE}"
        )
        self.not_verified_label.setStyleSheet(f"color: {colours[ItemState.INFO].name()};")
        self.not_verified_label.setVisible(unverified)

        rows = viewer.effective_params(rec, None if channel is None else channel.channel_index)
        for i, p in enumerate(rows):
            self.param_table.insertRow(i)
            for col, text in enumerate((p.scope, p.param, p.value, p.note)):
                self.param_table.setItem(i, col, _cell(text))
        _fit_height(self.param_table)
        self.param_table.setVisible(bool(rows))
        self.param_hint.setVisible(not rows)
        self.format_label.setText(viewer.format_text(rec))
        self.plan_label.setText(rec.recording_plan_ref or "")
        self.remarks_label.setText(rec.remarks or "")
        logged = f"by {rec.logged_by}"
        if rec.created_at:
            logged += f" on {viewer.iso_display(rec.created_at, self._offset)}"
        if rec.updated_at and rec.updated_at != rec.created_at:  # D47
            logged += f"; last changed on {viewer.iso_display(rec.updated_at, self._offset)}"
        if rec.archive_state is ArchiveState.ARCHIVED and rec.archived_at:
            logged += f"; archived on {viewer.iso_display(rec.archived_at, self._offset)}"
        self.logged_label.setText(logged)

        transfers = viewer.transfer_rows(details.transfers, self._offset)
        self.transfer_hint.setText("" if transfers else "No transfers yet.")
        self.transfer_hint.setVisible(not transfers)
        zone = offset_label(self._offset)
        self.transfer_table.setHorizontalHeaderLabels(
            (f"When ({zone})", "Operation", "Scope", "Result", "By")
        )
        for i, t in enumerate(transfers):
            self.transfer_table.insertRow(i)
            for col, text in enumerate((t.when, t.operation, t.scope, t.result, t.by)):
                self.transfer_table.setItem(i, col, _cell(text, t.notes))
        _fit_height(self.transfer_table)
        self.transfer_table.setVisible(bool(transfers))

    # =====================================================================
    # Gap scan
    # =====================================================================

    def start_scan(self) -> None:
        details = self._details
        if details is None or self._scan_task is not None:
            return
        rec = details.recording
        folder = viewer.recording_folder(rec)
        self._scan_id += 1
        scan_id = self._scan_id
        self._scan = None
        self._scan_note = (ItemState.TODO, "Scanning: 0 files")
        self._show_scan()

        def work(task: Task) -> ScanResult:
            return scan_recording(
                folder, rec.file_duration_s, progress=task.report, cancelled=task.is_cancelled
            )

        self._scan_task = self.runner.start(
            work,
            on_success=lambda result: self._scan_finished(scan_id, result),
            on_failure=lambda exc: self._scan_failed(scan_id, exc),
            on_progress=lambda n: self._scan_progress(scan_id, n),
        )
        self._update_buttons()

    def cancel_scan(self) -> None:
        if self._scan_task is not None:
            self._scan_task.cancel()
            self._scan_task = None
            self._scan_id += 1  # drop its result
            self._scan_note = (ItemState.TODO, "Scan cancelled.")
            self._show_scan()
            self._update_buttons()

    def _scan_progress(self, scan_id: int, n_files: int) -> None:
        if scan_id == self._scan_id:
            self._scan_note = (ItemState.TODO, f"Scanning: {n_files:,} files")
            self._show_scan()

    def _scan_finished(self, scan_id: int, result: object) -> None:
        if scan_id != self._scan_id or not isinstance(result, ScanResult):
            return
        self._scan_task = None
        self._scan = result
        total = sum(c.n_files for c in result.channels)
        self._scan_note = (ItemState.OK, f"Scanned {total:,} files.")
        self._show_scan()
        self._update_buttons()

    def _scan_failed(self, scan_id: int, exc: Exception) -> None:
        if scan_id != self._scan_id:
            return
        self._scan_task = None
        if isinstance(exc, ScanCancelled):
            self._scan_note = (ItemState.TODO, "Scan cancelled.")
        elif isinstance(exc, ScanError):
            self._scan_note = (
                ItemState.ERROR,
                "Cannot scan the folder: " + "; ".join(exc.problems),
            )
        else:
            self._scan_note = (ItemState.ERROR, f"Cannot scan the folder: {exc}")
        self._show_scan()
        self._update_buttons()

    def _reset_scan(self) -> None:
        self._scan = None
        self._scan_note = None
        self._show_scan()

    def _show_scan(self) -> None:
        colours = self._colours()
        has_details = self._details is not None
        if self._scan_note is None:
            self.scan_status.setText(SCAN_HINT if has_details else "")
            self.scan_status.setStyleSheet("")
        else:
            state, text = self._scan_note
            self.scan_status.setText(f"{MARKS[state]}  {text}")
            self.scan_status.setStyleSheet(f"color: {colours[state].name()};")
        scan, details = self._scan, self._details
        if scan is None or details is None:
            self.timeline.clear()
            self.timeline.setVisible(False)
            self.gap_label.setText("")
            self.gap_label.setVisible(False)
            self.difference_label.setText("")
            self.difference_label.setVisible(False)
            return
        zone = offset_label(self._offset)
        self.timeline.set_rows(viewer.timeline_rows(scan), self._offset)
        self.timeline.setVisible(True)
        self.gap_label.setText(
            f"Times in {zone}.\n" + "\n".join(viewer.gap_lines(scan, self._offset))
        )
        self.gap_label.setVisible(True)
        differences = viewer.scan_differences(details.recording, scan)
        mark = MARKS[ItemState.INFO]
        self.difference_label.setText("\n".join(f"{mark} {d}" for d in differences))
        self.difference_label.setStyleSheet(f"color: {colours[ItemState.INFO].name()};")
        self.difference_label.setVisible(bool(differences))

    # =====================================================================
    # Actions
    # =====================================================================

    def _update_buttons(self) -> None:
        has_db = bool(self.config.db_path)
        selected = self._details is not None and self._details.recording.id == self._selected_id
        self.refresh_button.setEnabled(has_db)
        self.apply_button.setEnabled(has_db)
        self.open_button.setEnabled(selected)
        self.edit_button.setEnabled(selected)
        scanning = self._scan_task is not None
        self.scan_button.setEnabled(selected and not scanning)
        self.cancel_scan_button.setEnabled(scanning)
        self.cancel_scan_button.setVisible(scanning)

    def open_folder(self) -> None:
        if self._details is None:
            return
        channel = self._selected_channel()
        rec = self._details.recording
        path = viewer.channel_path(rec, channel) if channel else viewer.recording_path(rec)
        if not self._open_folder(Path(path)):
            self._set_message(ItemState.ERROR, FOLDER_NOT_OPENED, path)

    def request_edit(self) -> None:
        if self._details is not None and self._details.recording.id is not None:
            self.edit_requested.emit(self._details.recording.id)
