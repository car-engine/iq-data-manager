"""Coverage timeline: one bar per channel with its gaps, and a time axis (SPEC section 5).

A custom-painted widget (DECISIONS.md D9). The data comes from a gap scan through
viewer.timeline_rows(). Times on the axis are at the display offset (D24).
"""

from collections.abc import Sequence

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from iqdm.entry import ItemState
from iqdm.gui.widgets.checklist import colours_for
from iqdm.timeutil import display_time
from iqdm.viewer import TimelineRow

LABEL_WIDTH = 44
ROW_HEIGHT = 22
BAR_HEIGHT = 12
AXIS_HEIGHT = 22
MARGIN = 8
TICKS = 5  # axis labels, including both ends
MIN_GAP_WIDTH = 2.0  # pixels, so a one-second gap in a long recording stays visible


def x_for(t: float, t0: float, t1: float, left: float, width: float) -> float:
    """The x position of time t on an axis from t0 at `left` to t1 at `left + width`."""
    if t1 <= t0:
        return left
    return left + (t - t0) / (t1 - t0) * width


def gap_rects(
    row: TimelineRow, t0: float, t1: float, left: float, width: float
) -> list[tuple[float, float]]:
    """(x, width) of each gap of a row, at least MIN_GAP_WIDTH wide."""
    rects = []
    for start, seconds in row.gaps:
        x = x_for(start, t0, t1, left, width)
        w = x_for(start + seconds, t0, t1, left, width) - x
        rects.append((x, max(w, MIN_GAP_WIDTH)))
    return rects


def axis_ticks(t0: float, t1: float, count: int = TICKS) -> list[float]:
    """`count` evenly spaced times from t0 to t1."""
    if count < 2 or t1 <= t0:
        return [t0]
    step = (t1 - t0) / (count - 1)
    return [t0 + i * step for i in range(count)]


class TimelineView(QWidget):
    """Bars for the channels of one recording. Data in the OK colour, gaps in amber.

    set_selection() marks a time range on chosen rows with a frame in the highlight
    colour, for the Archive / copy tab.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: tuple[TimelineRow, ...] = ()
        self._offset = 0.0
        self._selection: tuple[float | None, float | None, frozenset[str]] | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_selection(
        self, start: float | None, end: float | None, labels: frozenset[str] | None
    ) -> None:
        """Mark start to end (None: the edge of the timeline) on the rows with these
        labels. labels None removes the mark."""
        self._selection = None if labels is None else (start, end, labels)
        self.update()

    @property
    def selection(self) -> tuple[float | None, float | None, frozenset[str]] | None:
        return self._selection

    @property
    def rows(self) -> tuple[TimelineRow, ...]:
        return self._rows

    def set_rows(self, rows: Sequence[TimelineRow], offset_hours: float) -> None:
        self._rows = tuple(rows)
        self._offset = offset_hours
        self.updateGeometry()
        self.update()

    def clear(self) -> None:
        self.set_rows((), self._offset)

    def set_offset(self, offset_hours: float) -> None:
        self._offset = offset_hours
        self.update()

    def span(self) -> tuple[float, float] | None:
        if not self._rows:
            return None
        return min(r.start_unix for r in self._rows), max(r.end_unix for r in self._rows)

    def sizeHint(self) -> QSize:  # noqa: N802  (Qt override)
        height = MARGIN * 2 + len(self._rows) * ROW_HEIGHT + AXIS_HEIGHT if self._rows else 0
        return QSize(400, height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802  (Qt override)
        return QSize(200, self.sizeHint().height())

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802  (Qt override)
        span = self.span()
        if span is None:
            return
        t0, t1 = span
        palette = self.palette()
        colours = colours_for(palette)
        text = palette.color(QPalette.ColorRole.Text)
        track = palette.color(QPalette.ColorRole.Mid)
        left = float(LABEL_WIDTH)
        width = max(1.0, self.width() - LABEL_WIDTH - MARGIN)

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            for i, row in enumerate(self._rows):
                top = MARGIN + i * ROW_HEIGHT
                bar_top = top + (ROW_HEIGHT - BAR_HEIGHT) / 2
                painter.setPen(text)
                painter.drawText(
                    QRectF(0, top, LABEL_WIDTH - 6, ROW_HEIGHT),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    row.label,
                )
                painter.fillRect(QRectF(left, bar_top, width, BAR_HEIGHT), track)
                x0 = x_for(row.start_unix, t0, t1, left, width)
                x1 = x_for(row.end_unix, t0, t1, left, width)
                painter.fillRect(QRectF(x0, bar_top, x1 - x0, BAR_HEIGHT), colours[ItemState.OK])
                for x, w in gap_rects(row, t0, t1, left, width):
                    painter.fillRect(
                        QRectF(x, bar_top - 2, w, BAR_HEIGHT + 4), colours[ItemState.INFO]
                    )
                if self._selection is not None and row.label in self._selection[2]:
                    s0 = t0 if self._selection[0] is None else max(t0, self._selection[0])
                    s1 = t1 if self._selection[1] is None else min(t1, self._selection[1])
                    if s1 > s0:
                        xs = x_for(s0, t0, t1, left, width)
                        xe = x_for(s1, t0, t1, left, width)
                        pen = QPen(palette.color(QPalette.ColorRole.Highlight), 2)
                        painter.setPen(pen)
                        painter.drawRect(QRectF(xs, bar_top - 4, xe - xs, BAR_HEIGHT + 8))
            axis_top = MARGIN + len(self._rows) * ROW_HEIGHT
            painter.setPen(text)
            ticks = axis_ticks(t0, t1)
            for j, t in enumerate(ticks):
                x = x_for(t, t0, t1, left, width)
                label = display_time(t, self._offset)[11:]
                if j == 0:
                    align, rect = Qt.AlignmentFlag.AlignLeft, QRectF(x, axis_top, 100, AXIS_HEIGHT)
                elif j == len(ticks) - 1:
                    align = Qt.AlignmentFlag.AlignRight
                    rect = QRectF(x - 100, axis_top, 100, AXIS_HEIGHT)
                else:
                    align = Qt.AlignmentFlag.AlignHCenter
                    rect = QRectF(x - 50, axis_top, 100, AXIS_HEIGHT)
                painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, label)
        finally:
            painter.end()
