"""Archive / copy tab: archive recordings to the NAS or copy them to a local PC.

SPEC section 8. The logic lives in iqdm.movecopy and iqdm.transfer, which have no Qt.
This module builds the tab and runs every preview, transfer, check and deletion in
the TaskRunner.

One operation runs at a time. While it runs, the form is locked, a progress bar and
a Stop button show, and the other tabs stay usable. A stopped copy or archive is
listed under "Unfinished transfers", from where it can be resumed (D51) or forgotten.
Deleting the laptop copy needs a passed "Check before delete" (D55) and a Yes in a
dialog whose default is No.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iqdm import movecopy, transferqueue, viewer
from iqdm.config import Config
from iqdm.entry import ChecklistItem, ItemState, default_logged_by, format_mhz, format_size
from iqdm.gui.log_tab import NO_DATABASE
from iqdm.gui.widgets.checklist import MARKS, ChecklistView, colours_for
from iqdm.gui.widgets.timeline import TimelineView
from iqdm.gui.workers import Task, TaskRunner
from iqdm.models import ArchiveState, HashMode, Operation, Recording, TransferEntry, Verification
from iqdm.scan.scanner import ScanCancelled, ScanError
from iqdm.timeutil import display_time, offset_label, utc_now_iso
from iqdm.transfer.copier import CopyProgress, RetryNotice
from iqdm.transfer.delete import DeleteRefused
from iqdm.transfer.operations import (
    CHECK_NEEDS_HASHES,
    CheckOutcome,
    DeleteOutcome,
    Preview,
    TransferError,
    TransferOutcome,
    TransferRequest,
    check_archive,
    check_before_delete,
    compare_with_laptop,
    delete_laptop_copy,
    preview_transfer,
    run_transfer,
)
from iqdm.transfer.pathcheck import files_text
from iqdm.transfer.selection import SelectionError
from iqdm.transfer.verify import VerifyProgress
from iqdm.transferqueue import ItemResult, Phase, QueueError, QueueItem, QueueKind, QueueState

PROGRESS_EVERY_S = 0.1  # copy progress reaches the GUI at most this often
PAUSE_QUEUE_QUESTION = (
    "Pause the queue?\n\nThe running item stops after the part of a file it is copying. "
    "Files already copied stay. Resume continues with that item and does not copy them "
    "again.\n\nDuring a Check before delete, the check stops instead. The item is then "
    '"Archived, check needed": run Check before delete for it in the form.'
)
QUEUED_TEXT = {  # the form's transfer is already in the queue (D86)
    QueueState.WAITING: (
        "This transfer is waiting in the queue. Click Start under the queue to run it, or "
        "remove it from the queue to run it here."
    ),
    QueueState.PAUSED: (
        "This transfer is paused in the queue. Click Resume under the queue to continue "
        "it, or remove it from the queue to run it here."
    ),
}
QUEUE_HINT = (
    "Add recordings with Add to queue in the Viewer, or set one up in the form above "
    "and click Add to queue under the preview. Start runs them one after another."
)
QUEUE_EDIT_NOTE = (
    "The queue item is in the form. Change it, click Preview, then Add to queue puts it "
    "back in its place."
)
QUEUE_HEADERS = ("Recording", "State", "Operation", "Size", "Scope", "Destination")
QUEUE_NOTE_HINT = "Select an item to see its full state."
QUEUE_JOBS = {
    QueueKind.ARCHIVE: "archive",
    QueueKind.COPY: "copy",
    QueueKind.CHECK_ARCHIVE: "check archive",
}
NO_MANIFEST_FOLDER = (
    "The app has no settings folder for the file list that each transfer keeps, so it "
    "cannot copy. Start the app from your own Windows account."
)
STOP_COPY_QUESTION = (
    "Stop the {what}?\n\nFiles already copied stay in the destination. You can resume "
    'the {what} later from "Unfinished transfers".'
)


def hash_mode_text(mode: HashMode, fraction: float) -> str:
    if mode is HashMode.NONE:
        return "Sizes only"
    if mode is HashMode.SAMPLE:
        return f"Sizes, and hashes of {fraction * 100:g} % of the files"
    return "Sizes and hashes of every file"


def _cell(text: str, tooltip: str = "") -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if tooltip:
        item.setToolTip(tooltip)
    return item


def _bold(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


class TransferTab(QWidget):
    """Archive to the NAS, copy to a PC, check, compare and delete the laptop copy."""

    busy_changed = Signal(bool)
    status_changed = Signal(str)  # a short progress text, '' when idle
    recording_changed = Signal(int)  # a recording whose transfers or location changed
    pick_requested = Signal()  # the user wants to choose a recording in the Viewer

    def __init__(
        self,
        config: Config | None = None,
        *,
        manifests_dir: Path | None = None,
        runner: TaskRunner | None = None,
        performed_by: Callable[[], str] = default_logged_by,
        clock: Callable[[], float] = time.monotonic,
        preview_options: Mapping[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """preview_options go to preview_transfer(); tests pass stubs for the drive
        mapping, the free space and the long-path setting there."""
        super().__init__(parent)
        self._preview_options = dict(preview_options or {})
        self.config = Config() if config is None else config
        self._offset = self.config.display_utc_offset_hours
        self.manifests_dir = manifests_dir
        self.runner = TaskRunner(self) if runner is None else runner
        self._performed_by = performed_by
        self._clock = clock

        self._rec: Recording | None = None
        self._project: str | None = None  # of the recording shown (D73)
        self._transfers: list[TransferEntry] = []
        self._load_id = 0
        self._list_id = 0
        self._preview: Preview | None = None
        self._task: Task | None = None
        self._job = ""  # the running operation: preview, copy, archive, check, delete...
        self._meter = movecopy.RateMeter()
        self._result: tuple[ItemState, str] | None = None
        self._pending_resume: TransferEntry | None = None
        self._unfinished: list[TransferEntry] = []
        self._channel_boxes: dict[int, QCheckBox] = {}
        self._time_errors: dict[str, str] = {}
        self._message_text = ""  # the line above the preview, without its mark
        self._queue = transferqueue.TransferQueue()  # D81
        self._queue_running = False
        self._pause_requested = False
        self._queue_key: int | None = None  # the running queue item
        self._queue_status = ""  # "queue 2 of 5" while the queue runs
        self._pending_edit: QueueItem | None = None  # a queue item on its way to the form
        self._edit_position: int | None = None  # where Add to queue puts it back

        self._build()
        self._clear_recording()
        self.refresh_unfinished()

    # =====================================================================
    # Layout
    # =====================================================================

    def _build(self) -> None:
        form = QWidget()
        column = QVBoxLayout(form)
        column.addWidget(self._build_source())
        column.addWidget(self._build_operation())
        column.addWidget(self._build_scope())
        column.addWidget(self._build_destination())
        column.addWidget(self._build_verification())
        column.addWidget(self._build_queue())
        column.addWidget(self._build_laptop())
        column.addWidget(self._build_unfinished())
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form)

        layout = QHBoxLayout(self)
        layout.addWidget(scroll, 3)
        layout.addWidget(self._build_preview(), 2)

    def _build_source(self) -> QGroupBox:
        box = QGroupBox("Recording")
        self.id_spin = QSpinBox()
        self.id_spin.setRange(0, 2_000_000_000)
        self.id_spin.setSpecialValueText("none")
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(lambda: self.load_recording(self.id_spin.value()))
        self.pick_button = QPushButton("Pick in Viewer")
        self.pick_button.setToolTip("Select a recording in the Viewer, then click Archive / copy.")
        self.pick_button.clicked.connect(self.pick_requested.emit)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout()
        row.addWidget(QLabel("Recording ID"))
        row.addWidget(self.id_spin)
        row.addWidget(self.load_button)
        row.addWidget(self.pick_button)
        row.addStretch(1)
        layout = QVBoxLayout(box)
        layout.addLayout(row)
        layout.addWidget(self.source_label)
        layout.addWidget(self.path_label)
        return box

    def _build_operation(self) -> QGroupBox:
        box = QGroupBox("Operation")
        self.copy_radio = QRadioButton("Copy to a PC")
        self.archive_radio = QRadioButton("Archive to the NAS")
        self.copy_radio.setChecked(True)
        self.operation_group = QButtonGroup(self)
        self.operation_group.addButton(self.copy_radio)
        self.operation_group.addButton(self.archive_radio)
        self.copy_radio.toggled.connect(self._operation_changed)
        copy_note = QLabel(
            "Copies the files to a folder on a PC. The recording entry stays as it is."
        )
        archive_note = QLabel(
            "Copies the whole recording to the NAS and checks the copy. The recording then "
            "points at the NAS copy. The laptop copy stays until you delete it below."
        )
        for note in (copy_note, archive_note):
            note.setWordWrap(True)
        layout = QGridLayout(box)
        layout.addWidget(self.copy_radio, 0, 0)
        layout.addWidget(copy_note, 0, 1)
        layout.addWidget(self.archive_radio, 1, 0)
        layout.addWidget(archive_note, 1, 1)
        layout.setColumnStretch(1, 1)
        return box

    def _build_scope(self) -> QGroupBox:
        self.scope_box = QGroupBox("Scope")
        self.whole_radio = QRadioButton("Whole recording")
        self.range_radio = QRadioButton("Time range")
        self.whole_radio.setChecked(True)
        self.scope_group = QButtonGroup(self)
        self.scope_group.addButton(self.whole_radio)
        self.scope_group.addButton(self.range_radio)
        self.whole_radio.toggled.connect(self._scope_changed)
        self.from_label = QLabel()
        self.to_label = QLabel()
        self.from_edit = QLineEdit()
        self.to_edit = QLineEdit()
        self.from_unix_edit = QLineEdit()
        self.to_unix_edit = QLineEdit()
        for edit in (self.from_edit, self.to_edit):
            edit.setPlaceholderText(movecopy.TIME_HINT)
        for edit in (self.from_unix_edit, self.to_unix_edit):
            edit.setPlaceholderText("Unix seconds")
        self.from_edit.editingFinished.connect(lambda: self._time_edited("from", False))
        self.to_edit.editingFinished.connect(lambda: self._time_edited("to", False))
        self.from_unix_edit.editingFinished.connect(lambda: self._time_edited("from", True))
        self.to_unix_edit.editingFinished.connect(lambda: self._time_edited("to", True))
        self.range_note = QLabel(
            "A file is included when its time is at or after the start and before the end."
        )
        self.range_note.setWordWrap(True)
        self.time_error_label = QLabel()
        self.time_error_label.setWordWrap(True)
        self.channels_row = QHBoxLayout()
        self.channels_row.addStretch(1)  # the checkboxes go before it, on the left
        self.timeline = TimelineView()
        self.timeline_note = QLabel()
        self.timeline_note.setWordWrap(True)
        self._label_times()

        scope_row = QHBoxLayout()
        scope_row.addWidget(self.whole_radio)
        scope_row.addWidget(self.range_radio)
        scope_row.addStretch(1)
        times = QGridLayout()
        times.addWidget(self.from_label, 0, 0)
        times.addWidget(self.to_label, 0, 1)
        times.addWidget(QLabel("From (Unix)"), 0, 2)
        times.addWidget(QLabel("To (Unix)"), 0, 3)
        times.addWidget(self.from_edit, 1, 0)
        times.addWidget(self.to_edit, 1, 1)
        times.addWidget(self.from_unix_edit, 1, 2)
        times.addWidget(self.to_unix_edit, 1, 3)
        layout = QVBoxLayout(self.scope_box)
        layout.addLayout(scope_row)
        layout.addLayout(times)
        layout.addWidget(self.range_note)
        layout.addWidget(self.time_error_label)
        layout.addWidget(QLabel("Channels"))
        layout.addLayout(self.channels_row)
        layout.addWidget(self.timeline)
        layout.addWidget(self.timeline_note)
        return self.scope_box

    def _build_destination(self) -> QGroupBox:
        box = QGroupBox("Destination")
        self.dest_edit = QLineEdit()
        self.dest_edit.textEdited.connect(self._invalidate)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_destination)
        row = QHBoxLayout()
        row.addWidget(self.dest_edit, 1)
        row.addWidget(self.browse_button)
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("Destination folder"))
        layout.addLayout(row)
        return box

    def _build_verification(self) -> QGroupBox:
        box = QGroupBox("Check after the copy")
        self.hash_combo = QComboBox()
        self.hash_combo.setToolTip(
            "Every check compares the number of files and each file's size. A hash also "
            "compares the content, and reads each hashed file again."
        )
        self._fill_hash_modes()
        self.hash_combo.currentIndexChanged.connect(self._invalidate)
        layout = QFormLayout(box)
        layout.addRow("Compare", self.hash_combo)
        return box

    def _build_queue(self) -> QGroupBox:
        """The queue of transfers that run one after another (D81)."""
        box = QGroupBox("Queue")
        hint = QLabel(QUEUE_HINT)
        hint.setWordWrap(True)
        self.queue_table = QTableWidget(0, len(QUEUE_HEADERS))
        self.queue_table.setHorizontalHeaderLabels(QUEUE_HEADERS)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.queue_table.itemSelectionChanged.connect(self._update_buttons)
        self.queue_table.itemSelectionChanged.connect(self._show_queue_note)
        self.queue_table.setMinimumHeight(140)
        self.queue_note = QLabel(QUEUE_NOTE_HINT)  # the selected item's state in full
        self.queue_note.setWordWrap(True)
        self.queue_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.queue_nas_edit = QLineEdit()
        self.queue_nas_edit.setPlaceholderText("A folder in one of the NAS locations")
        self.queue_nas_edit.setToolTip(
            "Recordings on the laptop that you add from the Viewer are archived into this "
            "folder, each in a folder of its own name. Edit an item to change its folder."
        )
        self.queue_nas_button = QPushButton("Browse...")
        self.queue_nas_button.clicked.connect(self.browse_queue_folder)
        self.check_after_box = QCheckBox("After each archive, run Check before delete")
        self.check_after_box.setToolTip(
            "Reads each NAS copy again, past this PC's file cache, so the laptop copy can be "
            "deleted afterwards. Needs a check with hashes."
        )
        self.check_after_box.setChecked(True)
        self.start_queue_button = QPushButton("Start")
        self.start_queue_button.clicked.connect(self.start_queue)
        self.pause_queue_button = QPushButton("Pause")
        self.pause_queue_button.clicked.connect(lambda: self.pause_queue())
        self.edit_queue_button = QPushButton("Edit")
        self.edit_queue_button.setToolTip("Take the item back into the form to change it.")
        self.edit_queue_button.clicked.connect(self.edit_queue_item)
        self.remove_queue_button = QPushButton("Remove")
        self.remove_queue_button.clicked.connect(self.remove_queue_item)
        self.clear_queue_button = QPushButton("Clear finished")
        self.clear_queue_button.clicked.connect(self.clear_finished_queue)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("NAS folder for archives"))
        folder_row.addWidget(self.queue_nas_edit, 1)
        folder_row.addWidget(self.queue_nas_button)
        buttons = QHBoxLayout()
        for button in (
            self.start_queue_button,
            self.pause_queue_button,
            self.edit_queue_button,
            self.remove_queue_button,
            self.clear_queue_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(box)
        layout.addWidget(hint)
        layout.addLayout(folder_row)
        layout.addWidget(self.check_after_box)
        layout.addWidget(self.queue_table)
        layout.addWidget(self.queue_note)
        layout.addLayout(buttons)
        return box

    def _build_laptop(self) -> QGroupBox:
        self.laptop_box = QGroupBox("Checks and the laptop copy")
        self.laptop_label = QLabel()
        self.laptop_label.setWordWrap(True)
        self.check_delete_button = QPushButton("Check before delete")
        self.check_delete_button.setToolTip(
            "Reads the NAS copy again, past this PC's file cache, and compares it with the "
            "file list of the archive. Nothing is changed."
        )
        self.check_delete_button.clicked.connect(self.start_check_before_delete)
        self.delete_button = QPushButton("Delete laptop copy...")
        self.delete_button.clicked.connect(self.start_delete)
        self.check_archive_button = QPushButton("Check archive")
        self.check_archive_button.setToolTip(
            "Compares the NAS folder with the database entry: channels, file counts and "
            "sizes. Nothing is changed, except counts the database does not hold yet."
        )
        self.check_archive_button.clicked.connect(self.start_check_archive)
        self.compare_button = QPushButton("Compare with laptop copy...")
        self.compare_button.setToolTip(
            "For a recording logged where it lies on the NAS: compares the NAS folder with "
            "a folder on this laptop. A passed comparison removes the not-verified mark."
        )
        self.compare_button.clicked.connect(self.start_compare)
        buttons = QHBoxLayout()
        for button in (
            self.check_delete_button,
            self.delete_button,
            self.check_archive_button,
            self.compare_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self.laptop_box)
        layout.addWidget(self.laptop_label)
        layout.addLayout(buttons)
        return self.laptop_box

    def _build_unfinished(self) -> QGroupBox:
        box = QGroupBox("Unfinished transfers")
        self.unfinished_table = QTableWidget(0, 7)
        self.unfinished_table.verticalHeader().setVisible(False)
        self.unfinished_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.unfinished_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.unfinished_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.unfinished_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.unfinished_table.itemSelectionChanged.connect(self._update_buttons)
        self.unfinished_table.setMinimumHeight(120)
        self.unfinished_hint = QLabel()
        self.others_check = QCheckBox("Show other users")
        self.others_check.toggled.connect(self.refresh_unfinished)
        self.resume_button = QPushButton("Resume")
        self.resume_button.setToolTip(
            "Fills in the form from this transfer and runs the preview. Files already in "
            "place are not copied again."
        )
        self.resume_button.clicked.connect(self.resume_selected)
        self.forget_button = QPushButton("Forget...")
        self.forget_button.clicked.connect(self.forget_selected)
        self.refresh_list_button = QPushButton("Refresh")
        self.refresh_list_button.clicked.connect(self.refresh_unfinished)
        row = QHBoxLayout()
        row.addWidget(self.others_check)
        row.addStretch(1)
        row.addWidget(self.refresh_list_button)
        row.addWidget(self.resume_button)
        row.addWidget(self.forget_button)
        layout = QVBoxLayout(box)
        layout.addWidget(self.unfinished_hint)
        layout.addWidget(self.unfinished_table)
        layout.addLayout(row)
        self._label_unfinished()
        return box

    def _build_preview(self) -> QGroupBox:
        box = QGroupBox("Preview")
        self.files_value = _bold("")
        self.size_value = _bold("")
        self.missing_value = QLabel()
        self.missing_value.setWordWrap(True)
        self.time_value = _bold("")
        figures = QFormLayout()
        figures.addRow("Files", self.files_value)
        figures.addRow("Size", self.size_value)
        figures.addRow("Missing in range", self.missing_value)
        figures.addRow("Estimated time", self.time_value)
        self.preview_lines = ChecklistView()
        self.preview_lines.setMinimumHeight(140)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.preview_button = QPushButton("Preview")
        self.preview_button.setToolTip("Checks the selection and the destination. Writes nothing.")
        self.preview_button.clicked.connect(self.start_preview)
        self.run_button = QPushButton("Run copy")
        self.run_button.clicked.connect(self.start_run)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.add_queue_button = QPushButton("Add to queue")
        self.add_queue_button.setToolTip(
            "Adds this previewed transfer to the queue in place of running it now."
        )
        self.add_queue_button.clicked.connect(self.add_current_to_queue)
        self.phase_label = _bold("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QLabel()
        self.speed_label = QLabel()
        self.retry_label = QLabel()
        self.retry_label.setWordWrap(True)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.queued_label = QLabel()  # why Run is off: the queue holds this transfer (D86)
        self.queued_label.setWordWrap(True)
        self.queued_label.setVisible(False)

        buttons = QHBoxLayout()
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.run_button, 1)
        buttons.addWidget(self.add_queue_button)
        buttons.addWidget(self.stop_button)
        layout = QVBoxLayout(box)
        layout.addWidget(self.message_label)
        layout.addLayout(figures)
        layout.addWidget(self.preview_lines, 1)
        layout.addWidget(QLabel("Files"))
        layout.addWidget(self.file_list, 1)
        layout.addWidget(QLabel("A copy or an archive never replaces or deletes a file."))
        layout.addLayout(buttons)
        layout.addWidget(self.queued_label)
        layout.addWidget(self.phase_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.speed_label)
        layout.addWidget(self.retry_label)
        layout.addWidget(self.result_label)
        return box

    def _label_times(self) -> None:
        self.from_label.setText(movecopy.time_label("From", self._offset))
        self.to_label.setText(movecopy.time_label("To", self._offset))

    def _label_unfinished(self) -> None:
        zone = offset_label(self._offset)
        self.unfinished_table.setHorizontalHeaderLabels(
            (f"Started ({zone})", "Operation", "Recording", "Scope", "Destination", "State", "By")
        )

    def _fill_hash_modes(self) -> None:
        current = self.hash_combo.currentData() or self.config.default_hash_mode
        self.hash_combo.blockSignals(True)
        self.hash_combo.clear()
        for mode in (HashMode.NONE, HashMode.SAMPLE, HashMode.ALL):
            self.hash_combo.addItem(hash_mode_text(mode, self.config.hash_sample_fraction), mode)
        self.hash_combo.setCurrentIndex(max(0, self.hash_combo.findData(current)))
        self.hash_combo.blockSignals(False)

    # =====================================================================
    # State
    # =====================================================================

    @property
    def is_busy(self) -> bool:
        """True while an operation runs, including a preview, and while the queue runs."""
        return self._task is not None or self._queue_running

    @property
    def queue(self) -> list[QueueItem]:
        return self._queue.items

    @property
    def queue_running(self) -> bool:
        return self._queue_running

    def queue_waiting(self) -> int:
        """Items that have not run, or were paused. Closing the app drops them."""
        return self._queue.runnable_count()

    @property
    def job(self) -> str:
        return self._job

    @property
    def recording(self) -> Recording | None:
        return self._rec

    @property
    def preview(self) -> Preview | None:
        return self._preview

    @property
    def unfinished(self) -> list[TransferEntry]:
        return list(self._unfinished)

    @property
    def result(self) -> tuple[ItemState, str] | None:
        return self._result

    def laptop_state(self) -> movecopy.LaptopCopy | None:
        if self._rec is None:
            return None
        return movecopy.laptop_copy(self._rec, self._transfers)

    def operation(self) -> Operation:
        return Operation.ARCHIVE if self.archive_radio.isChecked() else Operation.COPY

    def hash_mode(self) -> HashMode:
        """The chosen hash mode. QComboBox keeps a StrEnum as plain text, so the text is
        turned back into a HashMode here."""
        return HashMode(self.hash_combo.currentData() or HashMode.SAMPLE)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802  (Qt override)
        """Pick the colour set again after a switch between light and dark."""
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ) and hasattr(self, "result_label"):
            self._show_result()
            self._show_queued(self._queued_item())
            self._show_time_errors()
            self._show_laptop()
        super().changeEvent(event)

    def _colours(self) -> dict[ItemState, QColor]:
        return colours_for(self.palette())

    def apply_config(self, config: Config) -> None:
        """Take a new configuration without a restart (D33). The app does not save the
        settings while an operation runs."""
        old = self.config
        self.config = config
        if config.display_utc_offset_hours != self._offset:
            self._offset = config.display_utc_offset_hours
            self._label_times()
            self._label_unfinished()
            self._set_time_fields_from_values()
            self._show_recording()
            self._show_unfinished()
        if (config.default_hash_mode, config.hash_sample_fraction) != (
            old.default_hash_mode,
            old.hash_sample_fraction,
        ):
            self._fill_hash_modes()
        if config.db_path != old.db_path:
            self._clear_recording()
            self.refresh_unfinished()
        self._invalidate()

    # =====================================================================
    # Loading a recording
    # =====================================================================

    def load_recording(self, recording_id: int) -> bool:
        """Load a recording into the form. False while an operation runs."""
        if self.is_busy:
            self._set_message(ItemState.INFO, "Wait until the running operation has finished.")
            return False
        db = self.config.db_path
        if not db:
            self._set_message(ItemState.TODO, NO_DATABASE)
            return False
        if recording_id <= 0:
            self._set_message(ItemState.TODO, "Enter a recording ID or pick one in the Viewer.")
            return False
        self._load_id += 1
        load_id = self._load_id
        self.source_label.setText("Loading\N{HORIZONTAL ELLIPSIS}")
        self.runner.start(
            lambda task: viewer.load_details(db, recording_id),
            on_success=lambda result: self._loaded(load_id, result),
            on_failure=lambda exc: self._load_failed(load_id, exc),
        )
        return True

    def _reload(self) -> None:
        """Read the shown recording and its transfers again, keeping the form."""
        if self._rec is not None and self._rec.id is not None and self.config.db_path:
            db, rid = self.config.db_path, self._rec.id
            self._load_id += 1
            load_id = self._load_id
            self.runner.start(
                lambda task: viewer.load_details(db, rid),
                on_success=lambda result: self._loaded(load_id, result, keep_form=True),
            )

    def recording_saved(self, recording_id: int) -> None:
        """The Log tab saved a recording. Load it again if it is the one shown, because
        its channels or folder may have changed."""
        if self._rec is not None and self._rec.id == recording_id and not self.is_busy:
            self.load_recording(recording_id)

    def _loaded(self, load_id: int, result: object, *, keep_form: bool = False) -> None:
        if load_id != self._load_id or not isinstance(result, viewer.Details):
            return
        same = self._rec is not None and self._rec.id == result.recording.id
        if self._pending_edit is None and not (keep_form and same):
            self._edit_position = None  # the form no longer holds an edited queue item
        self._rec = result.recording
        self._transfers = list(result.transfers)
        self._site = result.site_name
        self._project = result.project_name
        self._set_message(ItemState.OK, "")
        if not (keep_form and same):
            self._fill_form_for(result.recording)
        self._show_recording()
        self._show_laptop()
        resume, self._pending_resume = self._pending_resume, None
        if resume is not None and resume.recording_id == result.recording.id:
            self._fill_form_from(resume)
            self.start_preview()
        edit = self._pending_edit
        if edit is not None and edit.request is not None:
            if edit.recording_id == result.recording.id:
                self._pending_edit = None
                self._fill_form_from_request(edit.request)
                self._set_message(ItemState.INFO, QUEUE_EDIT_NOTE)
                self.start_preview()
            else:  # another recording was loaded in between
                self._put_back_edit()
        self._update_buttons()

    def _load_failed(self, load_id: int, exc: Exception) -> None:
        if load_id != self._load_id:
            return
        self._pending_resume = None
        self._put_back_edit()
        self._clear_recording()
        self._set_message(ItemState.ERROR, viewer.error_text(exc), str(exc))

    def _clear_recording(self) -> None:
        self._edit_position = None
        self._rec = None
        self._transfers = []
        self._site = ""
        self._project = None
        self._set_channel_boxes(())
        self.id_spin.setValue(0)
        self.dest_edit.clear()
        self.from_edit.clear()
        self.to_edit.clear()
        self.from_unix_edit.clear()
        self.to_unix_edit.clear()
        self._time_errors = {}
        self._show_time_errors()
        self._show_recording()
        self._show_laptop()
        self._invalidate()

    def _fill_form_for(self, rec: Recording) -> None:
        """Defaults for a newly loaded recording."""
        self.id_spin.setValue(rec.id or 0)
        local = rec.archive_state is ArchiveState.LOCAL
        (self.archive_radio if local else self.copy_radio).setChecked(True)
        self.whole_radio.setChecked(True)
        self._set_channel_boxes([c.channel_index for c in rec.channels])
        start, end = rec.start_unix, rec.end_unix
        self._set_times(start, end)
        self._fill_destination()
        self._invalidate()

    def _fill_form_from(self, entry: TransferEntry) -> None:
        """The form of a stored transfer, for Resume."""
        if self._rec is None:
            return
        values = movecopy.form_from_transfer(entry, self._rec)
        (
            self.archive_radio if values.operation is Operation.ARCHIVE else self.copy_radio
        ).setChecked(True)
        (self.whole_radio if values.whole else self.range_radio).setChecked(True)
        if not values.whole:
            self._set_times(values.start_unix, values.end_unix)
        for index, box in self._channel_boxes.items():
            box.setChecked(index in values.channels)
        self.dest_edit.setText(values.destination)
        self.hash_combo.setCurrentIndex(max(0, self.hash_combo.findData(values.hash_mode)))
        self._invalidate()

    def _fill_form_from_request(self, request: TransferRequest) -> None:
        """The form of a queue item, for Edit (D81)."""
        if self._rec is None:
            return
        archive = request.operation is Operation.ARCHIVE
        (self.archive_radio if archive else self.copy_radio).setChecked(True)
        whole = request.start_unix is None and request.end_unix is None
        (self.whole_radio if whole else self.range_radio).setChecked(True)
        if not whole:
            self._set_times(request.start_unix, request.end_unix)
        for index, box in self._channel_boxes.items():
            box.setChecked(request.channels is None or index in request.channels)
        self.dest_edit.setText(request.destination)
        self.hash_combo.setCurrentIndex(max(0, self.hash_combo.findData(request.hash_mode)))
        self._invalidate()

    def _fill_destination(self) -> None:
        if self._rec is None:
            return
        if self.operation() is Operation.COPY:
            self.dest_edit.setText(
                movecopy.default_copy_destination(
                    self.config.default_local_copy_root, self._rec.rel_path
                )
            )
        else:
            self.dest_edit.clear()
        self.dest_edit.setPlaceholderText(
            "A folder on this PC"
            if self.operation() is Operation.COPY
            else "A new folder in one of the NAS locations"
        )

    def _set_channel_boxes(self, indices: Sequence[int]) -> None:
        for box in self._channel_boxes.values():
            self.channels_row.removeWidget(box)
            box.deleteLater()
        self._channel_boxes = {}
        names = {}
        if self._rec is not None:
            names = {c.channel_index: c for c in self._rec.channels}
        for index in indices:
            ch = names.get(index)
            text = f"Ch {index}"
            if ch is not None:
                text += f" \N{MIDDLE DOT} {format_mhz(ch.fc_hz)} MHz"
                if ch.band:
                    text += f" \N{MIDDLE DOT} {ch.band}"
            box = QCheckBox(text)
            box.setChecked(True)
            box.toggled.connect(self._invalidate)
            self.channels_row.insertWidget(self.channels_row.count() - 1, box)
            self._channel_boxes[index] = box

    @property
    def channel_boxes(self) -> dict[int, QCheckBox]:
        return dict(self._channel_boxes)

    def _show_recording(self) -> None:
        rec = self._rec
        if rec is None:
            self.source_label.setText("No recording loaded.")
            self.path_label.setText("")
            self.timeline.clear()
            self.timeline.setVisible(False)
            self.timeline_note.setText("")
            return
        zone = offset_label(self._offset)
        fcs = sorted({format_mhz(c.fc_hz) for c in rec.channels})
        size = sum(c.total_bytes or 0 for c in rec.channels)
        state = viewer.state_text(rec.archive_state, viewer.is_unverified(rec, self._transfers))
        start = "" if rec.start_unix is None else display_time(rec.start_unix, self._offset)
        project = "" if self._project is None else f" \N{MIDDLE DOT} {self._project}"  # D73
        self.source_label.setText(
            f"{rec.id} \N{MIDDLE DOT} {start} ({zone}) \N{MIDDLE DOT} {self._site}{project} "
            f"\N{MIDDLE DOT} {len(rec.channels)} ch \N{MIDDLE DOT} {', '.join(fcs)} MHz "
            f"\N{MIDDLE DOT} {format_size(size)} \N{MIDDLE DOT} {state}"
        )
        self.path_label.setText(viewer.recording_path(rec))
        if self._preview is not None and self._preview.selection.scan is not None:
            rows = viewer.timeline_rows(self._preview.selection.scan)
            note = "Missing seconds from the preview's scan are amber."
        else:
            rows = [
                viewer.TimelineRow(
                    label=f"Ch {c.channel_index}", start_unix=c.start_unix, end_unix=c.end_unix
                )
                for c in rec.channels
            ]
            note = "The preview scans the folder and shows the missing seconds."
        self.timeline.set_rows(rows, self._offset)
        self.timeline.setVisible(True)
        self.timeline_note.setText(f"Times in {zone}. {note} The frame marks the selection.")
        self._show_selection()

    def _show_selection(self) -> None:
        if self._rec is None:
            self.timeline.set_selection(None, None, None)
            return
        labels = frozenset(f"Ch {i}" for i, box in self._channel_boxes.items() if box.isChecked())
        if self.operation() is Operation.ARCHIVE or self.whole_radio.isChecked():
            self.timeline.set_selection(
                None, None, frozenset(f"Ch {i}" for i in self._channel_boxes)
            )
            return
        start, end = self._time_value("from"), self._time_value("to")
        self.timeline.set_selection(start, end, labels)

    # =====================================================================
    # Form
    # =====================================================================

    def _operation_changed(self) -> None:
        archive = self.operation() is Operation.ARCHIVE
        if archive:
            self.whole_radio.setChecked(True)
            for box in self._channel_boxes.values():
                box.setChecked(True)
        self._fill_destination()
        self.run_button.setText("Run archive" if archive else "Run copy")
        self._invalidate()

    def _scope_changed(self) -> None:
        self._invalidate()

    def _set_times(self, start: float | None, end: float | None) -> None:
        for edit, unix_edit, value in (
            (self.from_edit, self.from_unix_edit, start),
            (self.to_edit, self.to_unix_edit, end),
        ):
            if value is None:
                edit.clear()
                unix_edit.clear()
            else:
                edit.setText(movecopy.format_time_input(value, self._offset))
                unix_edit.setText(movecopy.format_unix_input(value))
        self._time_errors = {}
        self._show_time_errors()

    def _set_time_fields_from_values(self) -> None:
        """Rewrite the local times at a new display offset from the Unix fields."""
        for key in ("from", "to"):
            value = self._time_value(key)
            local = self.from_edit if key == "from" else self.to_edit
            if value is not None:
                local.setText(movecopy.format_time_input(value, self._offset))
        self._label_times()

    def _time_value(self, key: str) -> float | None:
        unix_edit = self.from_unix_edit if key == "from" else self.to_unix_edit
        if key in self._time_errors:
            return None
        try:
            return movecopy.parse_unix_input(unix_edit.text())
        except ValueError:
            return None

    def _time_edited(self, key: str, from_unix: bool) -> None:
        local = self.from_edit if key == "from" else self.to_edit
        unix_edit = self.from_unix_edit if key == "from" else self.to_unix_edit
        name = "From" if key == "from" else "To"
        try:
            if from_unix:
                value = movecopy.parse_unix_input(unix_edit.text())
                local.setText(movecopy.format_time_input(value, self._offset))
            else:
                value = movecopy.parse_time_input(local.text(), self._offset)
                unix_edit.setText(movecopy.format_unix_input(value))
            self._time_errors.pop(key, None)
        except ValueError as exc:
            self._time_errors[key] = f"{name}: {exc}"
        self._show_time_errors()
        self._invalidate()

    def _show_time_errors(self) -> None:
        errors = list(self._time_errors.values())
        mark = MARKS[ItemState.ERROR]
        self.time_error_label.setText("\n".join(f"{mark} {e}" for e in errors))
        self.time_error_label.setStyleSheet(f"color: {self._colours()[ItemState.ERROR].name()};")
        self.time_error_label.setVisible(bool(errors))

    def form_input(self) -> movecopy.FormInput:
        return movecopy.FormInput(
            operation=self.operation(),
            recording=self._rec,
            whole=self.whole_radio.isChecked(),
            start_unix=self._time_value("from"),
            end_unix=self._time_value("to"),
            time_errors=tuple(self._time_errors.values()),
            channels=tuple(i for i, box in self._channel_boxes.items() if box.isChecked()),
            destination=self.dest_edit.text(),
            hash_mode=self.hash_mode(),
        )

    def _current_request(self) -> TransferRequest | None:
        try:
            return movecopy.request_from_form(self.form_input())
        except movecopy.FormError:
            return None

    def _invalidate(self, *_: object) -> None:
        """Drop a preview that no longer matches the form."""
        if self._preview is not None and self._current_request() != self._preview.request:
            self._preview = None
            self._show_preview()
            self._show_recording()
        self._show_selection()
        self._update_buttons()

    def browse_destination(self) -> None:
        start = self.dest_edit.text().strip()
        if not start:
            if self.operation() is Operation.ARCHIVE and self.config.nas_roots:
                start = self.config.nas_roots[0]
            else:
                start = self.config.default_local_copy_root or ""
        folder = QFileDialog.getExistingDirectory(self, "Choose the destination folder", start)
        if folder:
            self.dest_edit.setText(str(Path(folder)))
            self._invalidate()

    # =====================================================================
    # Preview
    # =====================================================================

    def start_preview(self) -> None:
        if self.is_busy or not self.config.db_path:
            return
        try:
            request = movecopy.request_from_form(self.form_input())
        except movecopy.FormError as exc:
            self._preview = None
            self._show_preview(problems=exc.messages)
            self._update_buttons()
            return
        db, config, options = self.config.db_path, self.config, self._preview_options
        self._preview = None
        self._show_preview()
        self._begin("preview", "Previewing")
        self.phase_label.setText("Scanning the source folder")

        def work(task: Task) -> Preview:
            return preview_transfer(
                db,
                request,
                config,
                progress=task.report,
                cancelled=task.is_cancelled,
                **options,
            )

        self._task = self.runner.start(
            work,
            on_success=self._preview_done,
            on_failure=self._preview_failed,
            on_progress=lambda n: self.progress_label.setText(f"{n:,} files found"),
        )
        self._update_buttons()

    def _preview_done(self, result: object) -> None:
        self._end()
        if not isinstance(result, Preview):
            return
        if result.request != self._current_request():
            self._show_preview()  # the form changed while the preview ran
            return
        self._preview = result
        self._show_preview()
        self._show_recording()
        self._update_buttons()

    def _preview_failed(self, exc: Exception) -> None:
        self._end()
        if isinstance(exc, ScanCancelled):
            self._set_result(ItemState.TODO, "Preview stopped.")
        elif isinstance(exc, ScanError):
            self._show_preview(problems=("Cannot scan the folder: " + "; ".join(exc.problems),))
        elif isinstance(exc, SelectionError):
            self._show_preview(problems=(str(exc),))
        else:
            self._show_preview(problems=(viewer.error_text(exc),), tooltip=str(exc))
        self._update_buttons()

    def _show_preview(self, *, problems: Sequence[str] = (), tooltip: str = "") -> None:
        preview = self._preview
        self.file_list.clear()
        if preview is None:
            for label in (self.files_value, self.size_value, self.missing_value, self.time_value):
                label.setText("")
            lines = [ChecklistItem(ItemState.ERROR, p) for p in problems]
            if not lines:
                lines = [ChecklistItem(ItemState.TODO, "Click Preview to check the transfer.")]
            self.preview_lines.set_items(lines)
            self.preview_lines.setToolTip(tooltip)
            return
        summary = movecopy.preview_summary(preview, self.config.network_speed_mb_s)
        self.files_value.setText(summary.files)
        self.size_value.setText(summary.size)
        self.missing_value.setText(summary.missing)
        self.time_value.setText(summary.time)
        self.preview_lines.set_items(summary.lines)
        self.preview_lines.setToolTip("")
        self.file_list.addItems(movecopy.file_list(preview))

    # =====================================================================
    # Running a copy or an archive
    # =====================================================================

    def start_run(self) -> None:
        preview = self._preview
        if self.is_busy or preview is None or not preview.ok or not self.config.db_path:
            return
        if preview.request != self._current_request():
            self._invalidate()
            return
        if self._queued_item() is not None:  # the queue continues it (D86)
            self._update_buttons()
            return
        if self.manifests_dir is None:
            self._set_result(ItemState.ERROR, NO_MANIFEST_FOLDER)
            return
        self._edit_position = None  # an edited queue item runs here instead
        db, manifests = self.config.db_path, self.manifests_dir
        workers, user = self.config.copy_workers, self._performed_by()
        archive = preview.request.operation is Operation.ARCHIVE
        self._begin("archive" if archive else "copy", "Archiving" if archive else "Copying")
        self.phase_label.setText("Copying")
        last = [0.0]

        def work(task: Task) -> TransferOutcome:
            def copy_progress(p: CopyProgress) -> None:
                now = time.monotonic()
                if now - last[0] >= PROGRESS_EVERY_S or p.files_done == p.files_total:
                    last[0] = now
                    task.report(p)

            return run_transfer(
                db,
                preview,
                performed_by=user,
                manifests_dir=manifests,
                workers=workers,
                copy_progress=copy_progress,
                verify_progress=task.report,
                copy_retry=task.report,
                cancelled=task.is_cancelled,
            )

        self._task = self.runner.start(
            work,
            on_success=self._run_done,
            on_failure=self._operation_failed,
            on_progress=self._progress,
        )
        self._update_buttons()

    def _progress(self, value: object) -> None:
        if isinstance(value, Phase):  # a queue item starts its next step (D81)
            self.phase_label.setText(value.text)
            self.progress_bar.setValue(0)
            self.progress_label.setText("")
            self.speed_label.setText("")
            self._meter = movecopy.RateMeter()
            return
        if isinstance(value, CopyProgress):
            self.phase_label.setText("Copying")
            self.progress_bar.setValue(movecopy.percent(value.bytes_done, value.bytes_total))
            self.progress_label.setText(movecopy.copy_progress_text(value))
            self._meter.add(self._clock(), value.bytes_done)
            self.speed_label.setText(movecopy.speed_text(self._meter, value.bytes_total))
            self.retry_label.setText("")
            self._status(movecopy.percent(value.bytes_done, value.bytes_total))
        elif isinstance(value, VerifyProgress):
            phase = self.phase_label.text()
            if phase != "Checking" and not phase.startswith("Check before delete"):
                self.phase_label.setText("Checking")
                self._meter = movecopy.RateMeter()
            done, total = (
                (value.bytes_done, value.bytes_total)
                if value.bytes_total
                else (value.files_done, value.files_total)
            )
            self.progress_bar.setValue(movecopy.percent(done, total))
            self.progress_label.setText(movecopy.verify_progress_text(value))
            if value.bytes_total:
                self._meter.add(self._clock(), value.bytes_done)
                self.speed_label.setText(movecopy.speed_text(self._meter, value.bytes_total))
            self._status(movecopy.percent(done, total))
        elif isinstance(value, RetryNotice):
            self.retry_label.setText(
                f"Retrying {value.rel_path} (attempt {value.attempt} of {value.attempts}) in "
                f"{value.pause_s:g} s: {value.message}"
            )
        elif isinstance(value, int):
            self.progress_label.setText(f"{value:,} done")

    def _status(self, pct: int) -> None:
        words = {
            "copy": "copying",
            "archive": "archiving",
            "check": "checking",
            "compare": "comparing",
            "delete": "deleting",
            "check archive": "checking",
        }
        word = words.get(self._job)
        if word:
            queue = f"{self._queue_status}, " if self._queue_running else ""
            self.status_changed.emit(f"{queue}{word} {pct} %")

    def _run_done(self, result: object) -> None:
        job = self._job
        self._end()
        if not isinstance(result, TransferOutcome):
            return
        what = "archive" if job == "archive" else "copy"
        if result.passed:
            text = f"The {what} passed its check. Transfer {result.transfer_id} is recorded."
            if job == "archive":
                text += " The recording now points at the NAS copy."
            self._set_result(ItemState.OK, text)
        elif result.verification is Verification.SKIPPED:
            self._set_result(
                ItemState.TODO,
                f'{result.notes} Resume it from "Unfinished transfers".',
            )
        else:
            self._set_result(ItemState.ERROR, f"The {what} failed. {result.notes or ''}")
        self._after_change()

    def _operation_failed(self, exc: Exception) -> None:
        self._end()
        if isinstance(exc, DeleteRefused):
            self._set_result(ItemState.ERROR, " ".join(exc.reasons) or "Refused.", exc.detail)
        elif isinstance(exc, ScanCancelled):
            self._set_result(ItemState.TODO, "Stopped.")
        elif isinstance(exc, ScanError):
            self._set_result(ItemState.ERROR, "Cannot scan the folder: " + "; ".join(exc.problems))
        elif isinstance(exc, (SelectionError, TransferError, ValueError)):
            self._set_result(ItemState.ERROR, str(exc))
        else:
            self._set_result(ItemState.ERROR, viewer.error_text(exc), str(exc))
        self._after_change()

    def _after_change(self) -> None:
        """Read the recording and the list again after anything that wrote to them."""
        if self._rec is not None and self._rec.id is not None:
            self.recording_changed.emit(self._rec.id)
        self._preview = None
        self._show_preview()
        self._reload()
        self.refresh_unfinished()
        self._update_buttons()

    # =====================================================================
    # Checks and deletion
    # =====================================================================

    def start_check_before_delete(self) -> None:
        state = self.laptop_state()
        if self.is_busy or state is None or state.archive is None or not state.can_check:
            return
        if state.archive.id is None or not self.config.db_path:
            return
        db, archive_id = self.config.db_path, state.archive.id
        mode = self.hash_mode()
        if mode is HashMode.NONE:  # sizes alone read no content (D55)
            self._set_result(ItemState.ERROR, CHECK_NEEDS_HASHES)
            return
        fraction, user = self.config.hash_sample_fraction, self._performed_by()
        self._begin("check", "Check before delete")
        self.phase_label.setText("Reading the NAS copy")

        def work(task: Task) -> CheckOutcome:
            return check_before_delete(
                db,
                archive_id,
                hash_mode=mode,
                sample_fraction=fraction,
                performed_by=user,
                progress=task.report,
                cancelled=task.is_cancelled,
            )

        self._task = self.runner.start(
            work,
            on_success=self._check_done,
            on_failure=self._operation_failed,
            on_progress=self._progress,
        )
        self._update_buttons()

    def start_check_archive(self) -> None:
        rec = self._rec
        if self.is_busy or rec is None or rec.id is None or not self.config.db_path:
            return
        if rec.archive_state is not ArchiveState.ARCHIVED:
            return
        db, rid, user = self.config.db_path, rec.id, self._performed_by()
        self._begin("check archive", "Check archive")
        self.phase_label.setText("Scanning the NAS folder")
        self._task = self.runner.start(
            lambda task: check_archive(
                db, rid, performed_by=user, progress=task.report, cancelled=task.is_cancelled
            ),
            on_success=self._check_done,
            on_failure=self._operation_failed,
            on_progress=lambda n: self.progress_label.setText(f"{n:,} files found"),
        )
        self._update_buttons()

    def start_compare(self) -> None:
        rec = self._rec
        if self.is_busy or rec is None or rec.id is None or not self.config.db_path:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Choose the recording folder on this laptop", ""
        )
        if not folder:
            return
        db, rid, user = self.config.db_path, rec.id, self._performed_by()
        mode = self.hash_mode()
        fraction = self.config.hash_sample_fraction
        self._begin("compare", "Compare with laptop copy")
        self.phase_label.setText("Scanning both folders")

        def work(task: Task) -> CheckOutcome:
            return compare_with_laptop(
                db,
                rid,
                Path(folder),
                hash_mode=mode,
                sample_fraction=fraction,
                performed_by=user,
                scan_progress=task.report,
                progress=task.report,
                cancelled=task.is_cancelled,
            )

        self._task = self.runner.start(
            work,
            on_success=self._check_done,
            on_failure=self._operation_failed,
            on_progress=self._progress,
        )
        self._update_buttons()

    def _check_done(self, result: object) -> None:
        self._end()
        if not isinstance(result, CheckOutcome):
            return
        state = {
            Verification.PASS: ItemState.OK,
            Verification.FAIL: ItemState.ERROR,
            Verification.SKIPPED: ItemState.INFO,
        }[result.verification]
        self._set_result(state, result.notes)
        self._after_change()

    def start_delete(self) -> None:
        state = self.laptop_state()
        rec = self._rec
        if self.is_busy or state is None or not state.can_delete or rec is None:
            return
        archive = state.archive
        if archive is None or archive.id is None or not self.config.db_path:
            return
        files = state.files_left if state.files_left is not None else archive.n_files or 0
        size = "" if archive.total_bytes is None else f" ({format_size(archive.total_bytes)})"
        answer = QMessageBox.question(
            self,
            "Delete the laptop copy?",
            f"Delete the laptop copy of recording {rec.id}?\n\n"
            f"{files_text(files)}{size} in {archive.source} will be deleted. "
            f"The NAS copy in {archive.destination} stays.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        db, archive_id, user = self.config.db_path, archive.id, self._performed_by()
        total = archive.n_files or files
        self._begin("delete", "Deleting the laptop copy")
        self.phase_label.setText("Deleting")
        self._task = self.runner.start(
            lambda task: delete_laptop_copy(
                db,
                archive_id,
                performed_by=user,
                progress=task.report,
                cancelled=task.is_cancelled,
            ),
            on_success=self._delete_done,
            on_failure=self._operation_failed,
            on_progress=lambda n: self._delete_progress(n, total),
        )
        self._update_buttons()

    def _delete_progress(self, done: int, total: int) -> None:
        self.progress_bar.setValue(movecopy.percent(done, total))
        self.progress_label.setText(f"{done:,} of {total:,} files")
        self._status(movecopy.percent(done, total))

    def _delete_done(self, result: object) -> None:
        self._end()
        if not isinstance(result, DeleteOutcome):
            return
        r = result.result
        if r.complete:
            self._set_result(ItemState.OK, f"Deleted {files_text(len(r.deleted))} from the laptop.")
        else:
            kept = "; ".join(f"{k.rel_path}: {k.reason}" for k in r.kept[:10])
            stopped = " Stopped before the end." if r.cancelled else ""
            self._set_result(
                ItemState.INFO if r.cancelled and not r.kept else ItemState.ERROR,
                f"Deleted {files_text(len(r.deleted))}.{stopped}"
                + (f" Kept {files_text(len(r.kept))}: {kept}" if r.kept else ""),
            )
        self._after_change()

    def _show_laptop(self) -> None:
        state = self.laptop_state()
        rec = self._rec
        text = "" if state is None else state.text
        if rec is not None and rec.archive_state is ArchiveState.ARCHIVED:
            if viewer.is_unverified(rec, self._transfers):
                note = f"{MARKS[ItemState.INFO]}  Not verified. {viewer.NOT_VERIFIED_NOTE}"
                text = f"{text}\n{note}".strip()
        elif rec is not None:
            text = "The recording is on the laptop. Archive it to the NAS first."
        self.laptop_label.setText(text or "Load a recording.")

    # =====================================================================
    # Queue (D81)
    # =====================================================================

    def browse_queue_folder(self) -> None:
        start = self.queue_nas_edit.text().strip() or (
            self.config.nas_roots[0] if self.config.nas_roots else ""
        )
        folder = QFileDialog.getExistingDirectory(self, "Choose the NAS folder for archives", start)
        if folder:
            self.queue_nas_edit.setText(str(Path(folder)))

    def add_current_to_queue(self) -> None:
        """Add the previewed transfer of the form to the queue, in place of Run."""
        preview, rec = self._preview, self._rec
        if self.is_busy or preview is None or not preview.ok or rec is None or rec.id is None:
            return
        if preview.request != self._current_request():
            self._invalidate()
            return
        request = preview.request
        kind = QueueKind.ARCHIVE if request.operation is Operation.ARCHIVE else QueueKind.COPY
        item = QueueItem(
            recording_id=rec.id,
            label=transferqueue.recording_label(rec, self._site, self._offset),
            kind=kind,
            request=request,
            size_bytes=preview.selection.total_bytes,
        )
        try:
            added = self._queue.add(item, self._edit_position)
        except QueueError as exc:
            self._set_result(ItemState.ERROR, str(exc))
            return
        self._edit_position = None
        self._set_message(ItemState.OK, "")
        self._set_result(ItemState.OK, f"Added to the queue: {added.label}.")
        self._show_queue()
        self._update_buttons()

    def add_recordings(self, recording_ids: Sequence[int], *, check_archive: bool = False) -> None:
        """Add recordings chosen in the Viewer to the queue (D81).

        A recording on the laptop is archived into the queue's NAS folder; an archived
        one is copied to the default copy folder. With check_archive, each item is a
        Check archive (O41). New archives and copies are previewed when the tab is idle.
        """
        db = self.config.db_path
        if not db:
            self._set_message(ItemState.TODO, NO_DATABASE)
            return
        ids = list(recording_ids)
        if not ids:
            return

        def load(task: Task) -> list[viewer.Details]:
            return [viewer.load_details(db, rid) for rid in ids]

        self.runner.start(
            load,
            on_success=lambda result: self._recordings_for_queue(result, check_archive),
            on_failure=lambda exc: self._set_result(
                ItemState.ERROR, viewer.error_text(exc), str(exc)
            ),
        )

    def _recordings_for_queue(self, result: object, check_archive: bool) -> None:
        if not isinstance(result, list):
            return
        added: list[QueueItem] = []
        problems: list[str] = []
        for details in result:
            rec = details.recording
            label = transferqueue.recording_label(rec, details.site_name, self._offset)
            try:
                item = transferqueue.item_for_recording(
                    rec,
                    check_archive_only=check_archive,
                    nas_folder=self.queue_nas_edit.text(),
                    config=self.config,
                    hash_mode=self.hash_mode(),
                    label=label,
                )
                added.append(self._queue.add(item))
            except QueueError as exc:
                problems.append(str(exc))
        count = len(added)
        text = f"Added {count} {'item' if count == 1 else 'items'} to the queue."
        if problems:
            text += " Not added: " + " ".join(problems)
        state = ItemState.OK if not problems else ItemState.INFO if added else ItemState.ERROR
        self._set_result(state, text)
        self._show_queue()
        self._update_buttons()
        keys = [i.key for i in added if i.request is not None]
        if keys and not self.is_busy:
            self._check_queue_items(keys)

    def _check_queue_items(self, keys: Sequence[int]) -> None:
        """Preview new queue items, for their size and any problem. Writes nothing."""
        db, config, options = self.config.db_path, self.config, self._preview_options
        if not db:
            return
        items = [self._queue.get(k) for k in keys]
        self._begin("preview", "Checking the new queue items")

        def work(task: Task) -> list[tuple[int, ItemResult]]:
            results = []
            for n, item in enumerate(items, start=1):
                if task.is_cancelled():
                    break
                task.report(n)
                result = transferqueue.preview_item(
                    db, item, config, cancelled=task.is_cancelled, preview_options=options
                )
                results.append((item.key, result))
            return results

        self._task = self.runner.start(
            work,
            on_success=self._queue_items_checked,
            on_failure=self._queue_check_failed,
            on_progress=lambda n: self.progress_label.setText(f"Item {n} of {len(items)}"),
        )
        self._update_buttons()

    def _queue_items_checked(self, result: object) -> None:
        self._end()
        if isinstance(result, list):
            keys = {i.key for i in self._queue.items if i.state is QueueState.WAITING}
            for key, item_result in result:
                if key in keys:
                    self._queue.set_result(key, item_result)
        self._show_queue()
        self._update_buttons()

    def _queue_check_failed(self, exc: Exception) -> None:
        self._end()
        self._set_result(ItemState.ERROR, viewer.error_text(exc), str(exc))

    def start_queue(self) -> None:
        """Run the waiting and paused items one after another."""
        if self.is_busy or not self.config.db_path:
            return
        if self.manifests_dir is None:
            self._set_result(ItemState.ERROR, NO_MANIFEST_FOLDER)
            return
        if not self._queue.runnable_count():
            self._set_result(ItemState.TODO, "The queue has nothing to run.")
            return
        self._queue_running = True
        self._pause_requested = False
        self._set_result(ItemState.OK, "")
        self.busy_changed.emit(True)
        self._run_next_item()

    def _run_next_item(self) -> None:
        item = None if self._pause_requested else self._queue.next_runnable()
        if item is None or not self.config.db_path or self.manifests_dir is None:
            self._finish_queue()
            return
        db, config, manifests = self.config.db_path, self.config, self.manifests_dir
        options, user = self._preview_options, self._performed_by()
        check_after = self.check_after_box.isChecked()
        position = self._queue.position(item.key) + 1
        self._queue.set_state(item.key, QueueState.RUNNING)
        self._queue_key = item.key
        self._queue_status = f"queue {position} of {len(self._queue)}"
        self._show_queue()
        self._begin(QUEUE_JOBS[item.kind], f"Queue item {position} of {len(self._queue)}")
        self.status_changed.emit(self._queue_status)
        last = [0.0]

        def work(task: Task) -> ItemResult:
            def copy_report(p: object) -> None:
                now = time.monotonic()
                if not isinstance(p, CopyProgress):
                    task.report(p)
                elif now - last[0] >= PROGRESS_EVERY_S or p.files_done == p.files_total:
                    last[0] = now
                    task.report(p)

            return transferqueue.run_item(
                db,
                item,
                config,
                performed_by=user,
                manifests_dir=manifests,
                check_after_archive=check_after,
                report=task.report,
                copy_report=copy_report,
                cancelled=task.is_cancelled,
                preview_options=options,
            )

        self._task = self.runner.start(
            work,
            on_success=lambda result: self._queue_item_done(item, result),
            on_failure=lambda exc: self._queue_item_failed(item, exc),
            on_progress=self._progress,
        )
        self._update_buttons()

    def _queue_item_done(self, item: QueueItem, result: object) -> None:
        self._end()
        if isinstance(result, ItemResult):
            self._finish_item(item, result)
        self._run_next_item()

    def _queue_item_failed(self, item: QueueItem, exc: Exception) -> None:
        self._end()
        if isinstance(exc, ScanCancelled):
            result = ItemResult(state=QueueState.PAUSED, note="Paused.")
        elif isinstance(exc, DeleteRefused):
            result = ItemResult(state=QueueState.FAILED, note=" ".join(exc.reasons) or "Refused.")
        elif isinstance(exc, (TransferError, ValueError)):
            result = ItemResult(state=QueueState.FAILED, note=str(exc))
        else:
            result = ItemResult(state=QueueState.FAILED, note=viewer.error_text(exc))
        self._finish_item(item, result)
        self._run_next_item()

    def _finish_item(self, item: QueueItem, result: ItemResult) -> None:
        if result.state is QueueState.PAUSED:
            self._pause_requested = True  # only a pause or a stop cancels an item
        if item.key in {i.key for i in self._queue.items}:
            self._queue.set_result(item.key, result)
        self._queue_key = None
        self.recording_changed.emit(item.recording_id)
        self.refresh_unfinished()
        self._show_queue()

    def _finish_queue(self) -> None:
        self._queue_running = False
        self._queue_key = None
        self._queue_status = ""
        items = self._queue.items
        counts = {s: sum(1 for i in items if i.state is s) for s in QueueState}
        shown_states = (
            QueueState.DONE,
            QueueState.CHECK_NEEDED,
            QueueState.FAILED,
            QueueState.NOT_STARTED,
        )
        # "; " between parts: "archived, check needed" holds a comma (D85).
        parts = [f"{counts[s]} {str(s).lower()}" for s in shown_states if counts[s]]
        waiting = counts[QueueState.WAITING] + counts[QueueState.PAUSED]
        if self._pause_requested and waiting:
            text = f"Queue paused. {waiting} left; Resume continues."
            state = ItemState.INFO
        else:
            text = "Queue finished."
            if counts[QueueState.FAILED]:
                state = ItemState.ERROR
            elif counts[QueueState.CHECK_NEEDED] or counts[QueueState.NOT_STARTED]:
                state = ItemState.INFO
            else:
                state = ItemState.OK
        if parts:
            text += " " + "; ".join(parts) + "."
        self._pause_requested = False
        if self._preview is not None:  # the queue may have copied into its destination (D86)
            self._preview = None
            self._show_preview()
        self._set_result(state, text)
        self.status_changed.emit("")
        self.busy_changed.emit(self.is_busy)
        self._show_queue()
        self._reload()
        self._update_buttons()

    def pause_queue(self, *, ask: bool = True) -> bool:
        """Pause the queue: the running item stops between chunks, as Stop does (D81).

        Returns True when a pause was requested.
        """
        if not self._queue_running or self._pause_requested:
            return False
        if ask:
            answer = QMessageBox.question(
                self,
                "Pause the queue?",
                PAUSE_QUEUE_QUESTION,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self._pause_requested = True
        if self._task is not None:
            self._task.cancel()
        self.phase_label.setText("Pausing\N{HORIZONTAL ELLIPSIS}")
        self._update_buttons()
        return True

    def _selected_queue_item(self) -> QueueItem | None:
        rows = self.queue_table.selectionModel().selectedRows()
        items = self._queue.items
        if not rows or rows[0].row() >= len(items):
            return None
        return items[rows[0].row()]

    def select_queue_row(self, row: int) -> None:
        self.queue_table.selectRow(row)

    def remove_queue_item(self) -> None:
        item = self._selected_queue_item()
        if item is None:
            return
        try:
            self._queue.remove(item.key)
        except QueueError as exc:
            self._set_result(ItemState.ERROR, str(exc))
            return
        self._show_queue()
        self._update_buttons()

    def edit_queue_item(self) -> None:
        """Take an item back into the form. Add to queue puts it back in its place."""
        item = self._selected_queue_item()
        if self.is_busy or item is None or item.request is None:
            return
        position = self._queue.position(item.key)
        self._queue.remove(item.key)
        self._pending_edit = item
        self._edit_position = position
        self._show_queue()
        if not self.load_recording(item.recording_id):
            self._put_back_edit()

    def _put_back_edit(self) -> None:
        """Return a queue item whose recording could not be loaded for Edit."""
        item, self._pending_edit = self._pending_edit, None
        if item is None:
            return
        try:
            self._queue.add(item, self._edit_position)
        except QueueError as exc:  # an equal item was added meanwhile
            self._set_result(ItemState.INFO, f"The edited item was not put back. {exc}")
        self._edit_position = None
        self._show_queue()

    def clear_finished_queue(self) -> None:
        self._queue.clear_finished()
        self._show_queue()
        self._update_buttons()

    def _show_queue(self) -> None:
        table = self.queue_table
        selected = self._selected_queue_item()
        table.setRowCount(0)
        colours = self._colours()
        states = {
            QueueState.DONE: ItemState.OK,
            QueueState.CHECK_NEEDED: ItemState.INFO,  # the laptop copy cannot go yet (D85)
            QueueState.FAILED: ItemState.ERROR,
            QueueState.NOT_STARTED: ItemState.ERROR,
            QueueState.PAUSED: ItemState.TODO,
            QueueState.RUNNING: ItemState.INFO,
        }
        for row, item in enumerate(self._queue.items):
            table.insertRow(row)
            size = "" if item.size_bytes is None else format_size(item.size_bytes)
            look = states.get(item.state)
            if item.state is QueueState.WAITING and item.note:
                look = ItemState.INFO  # a problem the preview found when it was added
            word = str(item.state) if look is None else f"{MARKS[look]}  {item.state}"
            state_cell = _cell(word, transferqueue.state_text(item))
            if look is not None:
                state_cell.setForeground(colours[look])
            values = (
                _cell(item.label),
                state_cell,
                _cell(str(item.kind)),
                _cell(size),
                _cell(transferqueue.scope_text(item, self._offset)),
                _cell(item.destination, item.destination),
            )
            for col, cell in enumerate(values):
                table.setItem(row, col, cell)
            if selected is not None and item.key == selected.key:
                table.selectRow(row)
        self._show_queue_note()

    def _show_queue_note(self) -> None:
        item = self._selected_queue_item()
        if item is None:
            self.queue_note.setText(QUEUE_NOTE_HINT if self._queue.items else "")
        else:
            self.queue_note.setText(f"{item.label}: {transferqueue.state_text(item)}")

    # =====================================================================
    # Unfinished transfers
    # =====================================================================

    def refresh_unfinished(self) -> None:
        db = self.config.db_path
        if not db:
            self._unfinished = []
            self._show_unfinished()
            return
        self._list_id += 1
        list_id = self._list_id
        user = None if self.others_check.isChecked() else self._performed_by()
        self.runner.start(
            lambda task: movecopy.load_unfinished(db, user),
            on_success=lambda result: self._unfinished_loaded(list_id, result),
            on_failure=lambda exc: self._unfinished_failed(list_id, exc),
        )

    def _unfinished_loaded(self, list_id: int, result: object) -> None:
        if list_id != self._list_id or not isinstance(result, list):
            return
        self._unfinished = result
        self._show_unfinished()
        self._update_buttons()

    def _unfinished_failed(self, list_id: int, exc: Exception) -> None:
        if list_id == self._list_id:
            self._unfinished = []
            self._show_unfinished()
            self.unfinished_hint.setText(viewer.error_text(exc))
            self.unfinished_hint.setToolTip(str(exc))

    def _show_unfinished(self) -> None:
        table = self.unfinished_table
        table.setRowCount(0)
        self.unfinished_hint.setToolTip("")
        if not self._unfinished:
            self.unfinished_hint.setText("No unfinished copies or archives.")
            self._update_buttons()
            return
        self.unfinished_hint.setText(
            "Copies and archives that were stopped, failed or never finished."
        )
        rows = viewer.transfer_rows(self._unfinished, self._offset)
        for i, (entry, shown) in enumerate(zip(self._unfinished, rows, strict=True)):
            table.insertRow(i)
            state = movecopy.unfinished_state(entry)
            values = (
                _cell(shown.when),
                _cell(movecopy.operation_name(entry.operation)),
                _cell(f"Recording {entry.recording_id}"),
                _cell(shown.scope),
                _cell(entry.destination or ""),
                _cell(state if not entry.notes else f"{state}: {entry.notes}", entry.notes or ""),
                _cell(entry.performed_by),
            )
            for col, item in enumerate(values):
                table.setItem(i, col, item)
        self._update_buttons()

    def _selected_unfinished(self) -> TransferEntry | None:
        rows = self.unfinished_table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._unfinished):
            return None
        return self._unfinished[rows[0].row()]

    def select_unfinished(self, row: int) -> None:
        self.unfinished_table.selectRow(row)

    def resume_selected(self) -> None:
        entry = self._selected_unfinished()
        if entry is None or self.is_busy:
            return
        self._pending_resume = entry
        if not self.load_recording(entry.recording_id):
            self._pending_resume = None

    def forget_selected(self) -> None:
        entry = self._selected_unfinished()
        if entry is None or entry.id is None or self.is_busy or not self.config.db_path:
            return
        answer = QMessageBox.question(
            self,
            "Forget this transfer?",
            f"Remove the {movecopy.operation_name(entry.operation).lower()} of recording "
            f"{entry.recording_id} from this list?\n\nThe files already copied stay in "
            f"{entry.destination}. Delete that folder by hand if you no longer need it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        db, tid = self.config.db_path, entry.id
        self.runner.start(
            lambda task: movecopy.forget_transfer(db, tid, now=utc_now_iso()),
            on_success=lambda _r: self.refresh_unfinished(),
            on_failure=lambda exc: self._set_result(
                ItemState.ERROR, viewer.error_text(exc), str(exc)
            ),
        )

    # =====================================================================
    # Running state
    # =====================================================================

    def _begin(self, job: str, title: str) -> None:
        self._job = job
        self._meter = movecopy.RateMeter()
        self._result = None
        self._show_result()
        self.phase_label.setText(title)
        self.progress_bar.setValue(0)
        self.progress_label.setText("")
        self.speed_label.setText("")
        self.retry_label.setText("")
        for widget in (self.phase_label, self.progress_bar, self.progress_label):
            widget.setVisible(True)
        self.busy_changed.emit(True)

    def _end(self) -> None:
        self._task = None
        self._job = ""
        for widget in (
            self.phase_label,
            self.progress_bar,
            self.progress_label,
            self.speed_label,
            self.retry_label,
        ):
            widget.setVisible(False)
        self.status_changed.emit(self._queue_status if self._queue_running else "")
        self.busy_changed.emit(self.is_busy)  # still busy between queue items
        self._update_buttons()

    def stop(self, *, ask: bool = True) -> bool:
        """Stop the running operation. For a copy or an archive, ask first unless ask is
        False. While the queue runs, this pauses it. Returns True when a stop was
        requested."""
        if self._queue_running:
            return self.pause_queue(ask=ask)
        task = self._task
        if task is None:
            return False
        if ask and self._job in ("copy", "archive"):
            answer = QMessageBox.question(
                self,
                f"Stop the {self._job}?",
                STOP_COPY_QUESTION.format(what=self._job),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        task.cancel()
        self.phase_label.setText("Stopping\N{HORIZONTAL ELLIPSIS}")
        self.stop_button.setEnabled(False)
        return True

    def wait_until_idle(self, msecs: int = -1) -> bool:
        """Block until every task of the tab has ended. For closing the app and tests."""
        return self.runner.wait(msecs)

    def _queued_item(self) -> QueueItem | None:
        """The queue item that the form's previewed transfer repeats, or None (D86)."""
        preview = self._preview
        return None if preview is None else self._queue.holding(preview.request)

    def _show_queued(self, item: QueueItem | None) -> None:
        text = "" if item is None else QUEUED_TEXT.get(item.state, "")
        self.queued_label.setText(f"{MARKS[ItemState.INFO]}  {text}" if text else "")
        self.queued_label.setStyleSheet(f"color: {self._colours()[ItemState.INFO].name()};")
        self.queued_label.setVisible(bool(text))

    def _set_result(self, state: ItemState, text: str, tooltip: str = "") -> None:
        self._result = (state, text) if text else None
        self.result_label.setToolTip(tooltip)
        self._show_result()

    def _show_result(self) -> None:
        if self._result is None:
            self.result_label.setText("")
            self.result_label.setVisible(False)
            return
        state, text = self._result
        self.result_label.setText(f"{MARKS[state]}  {text}")
        self.result_label.setStyleSheet(f"color: {self._colours()[state].name()};")
        self.result_label.setVisible(True)

    def _set_message(self, state: ItemState, text: str, tooltip: str = "") -> None:
        self._message_text = text
        self.message_label.setText(f"{MARKS[state]}  {text}" if text else "")
        self.message_label.setToolTip(tooltip)
        self.message_label.setStyleSheet(f"color: {self._colours()[state].name()};")
        self.message_label.setVisible(bool(text))

    def _update_buttons(self) -> None:
        busy = self.is_busy
        has_db = bool(self.config.db_path)
        loaded = self._rec is not None
        archive = self.operation() is Operation.ARCHIVE
        for widget in (
            self.id_spin,
            self.load_button,
            self.pick_button,
            self.copy_radio,
            self.archive_radio,
            self.dest_edit,
            self.browse_button,
            self.hash_combo,
            self.resume_button,
            self.forget_button,
            self.refresh_list_button,
            self.others_check,
        ):
            widget.setEnabled(not busy)
        self.archive_radio.setEnabled(
            not busy
            and loaded
            and self._rec is not None
            and self._rec.archive_state is ArchiveState.LOCAL
        )
        range_ok = not busy and loaded and not archive
        self.whole_radio.setEnabled(range_ok)
        self.range_radio.setEnabled(range_ok)
        timed = range_ok and self.range_radio.isChecked()
        for edit in (self.from_edit, self.to_edit, self.from_unix_edit, self.to_unix_edit):
            edit.setEnabled(timed)
        for box in self._channel_boxes.values():
            box.setEnabled(range_ok)
        self.preview_button.setEnabled(not busy and loaded and has_db)
        preview = self._preview
        runnable = (
            not busy
            and preview is not None
            and preview.ok
            and preview.request == self._current_request()
        )
        queued = self._queued_item() if runnable else None
        self.run_button.setEnabled(runnable and queued is None)
        self.add_queue_button.setEnabled(runnable and queued is None)
        self._show_queued(queued)
        self.stop_button.setEnabled(busy and self._task is not None)
        self.stop_button.setVisible(busy and not self._queue_running)
        chosen = self._selected_queue_item()
        self.start_queue_button.setText("Resume" if self._queue.has_paused() else "Start")
        self.start_queue_button.setEnabled(
            not busy and has_db and self._queue.runnable_count() > 0
        )
        self.pause_queue_button.setEnabled(self._queue_running and not self._pause_requested)
        self.edit_queue_button.setEnabled(  # an archive already done cannot run again
            not busy
            and chosen is not None
            and chosen.request is not None
            and chosen.state is not QueueState.CHECK_NEEDED
        )
        self.remove_queue_button.setEnabled(
            chosen is not None and chosen.state is not QueueState.RUNNING
        )
        self.clear_queue_button.setEnabled(
            any(i.state in transferqueue.FINISHED for i in self._queue.items)
        )
        state = self.laptop_state()
        self.check_delete_button.setEnabled(not busy and state is not None and state.can_check)
        self.delete_button.setEnabled(not busy and state is not None and state.can_delete)
        archived = (
            loaded and self._rec is not None and (self._rec.archive_state is ArchiveState.ARCHIVED)
        )
        self.check_archive_button.setEnabled(not busy and archived)
        unverified = (
            archived and self._rec is not None and viewer.is_unverified(self._rec, self._transfers)
        )
        self.compare_button.setEnabled(not busy and unverified)
        self.compare_button.setVisible(unverified)
        selected = self._selected_unfinished() is not None
        self.resume_button.setEnabled(not busy and selected)
        self.forget_button.setEnabled(not busy and selected)
        if not has_db:
            self._set_message(ItemState.TODO, NO_DATABASE)
        elif self._message_text == NO_DATABASE:  # a path was saved since
            self._set_message(ItemState.OK, "")
