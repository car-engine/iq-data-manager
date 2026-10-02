"""Table model for the Viewer's recordings list (SPEC section 5).

A model over RecordingSummary rows, so thousands of recordings load quickly (O16).
SORT_ROLE gives each cell a value that sorts as a number or a date. Coverage below
the threshold is shown in amber with a mark (D39). A recording logged in place on
the NAS shows "not verified" in amber (D2).
"""

from collections.abc import Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor

from iqdm import viewer
from iqdm.entry import ItemState
from iqdm.gui.widgets.checklist import LIGHT_COLOURS, MARKS
from iqdm.models import RecordingSummary
from iqdm.timeutil import display_time, offset_label

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
ID_ROLE = Qt.ItemDataRole.UserRole + 2

COL_ID, COL_START, COL_SITE, COL_CH, COL_FC, COL_SPAN, COL_COVERAGE, COL_SIZE = range(8)
COL_STATE, COL_LOGGED_BY = 8, 9
COLUMN_COUNT = 10
_RIGHT = (COL_ID, COL_CH, COL_SPAN, COL_COVERAGE, COL_SIZE)  # numbers align right

UNKNOWN_COVERAGE_TOOLTIP = "The number of files is not in the database."
UNKNOWN_SIZE_TOOLTIP = "The size of the files is not in the database."

type _Index = QModelIndex | QPersistentModelIndex


def headers(zone: str) -> tuple[str, ...]:
    """Column headings, with the start time in the display zone such as 'UTC+8' (D24)."""
    return (
        "ID",
        f"Start ({zone})",
        "Site",
        "Ch",
        "Centre freq (MHz)",
        "Span",
        "Coverage",
        "Size",
        "State",
        "Logged by",
    )


def low_coverage_tooltip(threshold_percent: float) -> str:
    return (
        f"Below {threshold_percent:g}%: some seconds of the recording have no data file. "
        "Select the recording and scan for gaps to see where."
    )


class RecordingTableModel(QAbstractTableModel):
    """Read-only rows of the recordings list."""

    def __init__(self, offset_hours: float, threshold_percent: float) -> None:
        super().__init__()
        self._rows: list[RecordingSummary] = []
        self._offset = offset_hours
        self._threshold = threshold_percent
        self._colours: dict[ItemState, QColor] = LIGHT_COLOURS

    # ---- settings -------------------------------------------------------

    def set_rows(self, rows: Sequence[RecordingSummary]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def set_offset(self, offset_hours: float) -> None:
        self._offset = offset_hours
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, COL_START, COL_START)
        self._all_changed()

    def set_threshold(self, threshold_percent: float) -> None:
        self._threshold = threshold_percent
        self._all_changed()

    def set_colours(self, colours: dict[ItemState, QColor]) -> None:
        self._colours = colours
        self._all_changed()

    def _all_changed(self) -> None:
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, COLUMN_COUNT - 1)
            )

    # ---- access ---------------------------------------------------------

    def summary(self, row: int) -> RecordingSummary:
        return self._rows[row]

    def row_of(self, recording_id: int) -> int | None:
        for i, s in enumerate(self._rows):
            if s.id == recording_id:
                return i
        return None

    def is_low(self, summary: RecordingSummary) -> bool:
        return viewer.coverage_is_low(summary.coverage, self._threshold)

    # ---- QAbstractTableModel ------------------------------------------

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else COLUMN_COUNT

    def headerData(  # noqa: N802  (Qt override)
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return headers(offset_label(self._offset))[section]
        return None

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        s = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._text(s, col)
        if role == SORT_ROLE:
            return self._sort_key(s, col)
        if role == ID_ROLE:
            return s.id
        if role == Qt.ItemDataRole.ForegroundRole:
            if (col == COL_COVERAGE and self.is_low(s)) or (col == COL_STATE and s.unverified):
                return self._colours[ItemState.INFO]
            return None
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(s, col)
        if role == Qt.ItemDataRole.TextAlignmentRole and col in _RIGHT:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def _text(self, s: RecordingSummary, col: int) -> str:
        match col:
            case 0:
                return str(s.id)
            case 1:
                return display_time(s.start_unix, self._offset)[:16]
            case 2:
                return s.site_name
            case 3:
                return str(s.channel_count)
            case 4:
                return viewer.fc_summary(s.fc_hz)
            case 5:
                return viewer.span_text(s.end_unix - s.start_unix)
            case 6:
                text = viewer.coverage_text(s.coverage)
                return f"{MARKS[ItemState.INFO]} {text}" if self.is_low(s) else text
            case 7:
                return viewer.size_text(s.total_bytes)
            case 8:
                return viewer.state_text(s.archive_state, s.unverified)
            case _:
                return s.logged_by

    def _sort_key(self, s: RecordingSummary, col: int) -> object:
        match col:
            case 0:
                return s.id
            case 1:
                return s.start_unix
            case 2:
                return s.site_name.casefold()
            case 3:
                return s.channel_count
            case 4:
                return s.fc_hz[0] if s.fc_hz else -1.0
            case 5:
                return s.end_unix - s.start_unix
            case 6:
                return -1.0 if s.coverage is None else s.coverage
            case 7:
                return -1 if s.total_bytes is None else s.total_bytes
            case 8:
                return viewer.state_text(s.archive_state, s.unverified)
            case _:
                return s.logged_by.casefold()

    def _tooltip(self, s: RecordingSummary, col: int) -> str | None:
        if col == COL_COVERAGE:
            if s.coverage is None:
                return UNKNOWN_COVERAGE_TOOLTIP
            if self.is_low(s):
                return low_coverage_tooltip(self._threshold)
        if col == COL_SIZE and s.total_bytes is None:
            return UNKNOWN_SIZE_TOOLTIP
        if col == COL_STATE and s.unverified:
            return viewer.NOT_VERIFIED_NOTE
        return None
