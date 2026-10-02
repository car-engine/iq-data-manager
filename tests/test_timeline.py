"""Tests for the coverage timeline widget (pytest-qt, offscreen)."""

import pytest
from PySide6.QtGui import QColor, QImage, QPalette

from iqdm.entry import ItemState
from iqdm.gui.widgets.checklist import DARK_COLOURS, LIGHT_COLOURS
from iqdm.gui.widgets.timeline import (
    LABEL_WIDTH,
    MARGIN,
    MIN_GAP_WIDTH,
    ROW_HEIGHT,
    TimelineView,
    axis_ticks,
    gap_rects,
    x_for,
)
from iqdm.viewer import TimelineRow

T0 = 1790733600.0


def test_x_for_maps_the_span_to_the_width():
    assert x_for(T0, T0, T0 + 100, 40, 200) == 40
    assert x_for(T0 + 50, T0, T0 + 100, 40, 200) == 140
    assert x_for(T0 + 100, T0, T0 + 100, 40, 200) == 240
    assert x_for(T0, T0, T0, 40, 200) == 40  # an empty span does not divide by zero


def test_gap_rects_have_a_minimum_width():
    row = TimelineRow(
        label="Ch 0", start_unix=T0, end_unix=T0 + 3600, gaps=((T0 + 1800, 1.0), (T0, 900.0))
    )
    rects = gap_rects(row, T0, T0 + 3600, 0, 360)
    assert rects[0] == (180.0, MIN_GAP_WIDTH)  # 1 s is 0.1 px
    assert rects[1] == (0.0, 90.0)


def test_axis_ticks():
    assert axis_ticks(T0, T0 + 100) == [T0, T0 + 25, T0 + 50, T0 + 75, T0 + 100]
    assert axis_ticks(T0, T0) == [T0]


def palette(dark: bool) -> QPalette:
    pal = QPalette()
    base = QColor(45, 45, 45) if dark else QColor(255, 255, 255)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.Window, base)
    pal.setColor(QPalette.ColorRole.Text, QColor(230, 230, 230) if dark else QColor(0, 0, 0))
    pal.setColor(QPalette.ColorRole.Mid, QColor(90, 90, 90) if dark else QColor(200, 200, 200))
    return pal


@pytest.mark.parametrize(("dark", "colours"), [(False, LIGHT_COLOURS), (True, DARK_COLOURS)])
def test_paints_data_and_gaps_in_the_theme_colours(qtbot, dark, colours):
    view = TimelineView()
    qtbot.addWidget(view)
    view.setPalette(palette(dark))
    rows = [
        TimelineRow(label="Ch 0", start_unix=T0, end_unix=T0 + 100),
        TimelineRow(label="Ch 1", start_unix=T0, end_unix=T0 + 100, gaps=((T0 + 50, 10.0),)),
    ]
    view.set_rows(rows, 8.0)
    view.resize(LABEL_WIDTH + MARGIN + 200, view.sizeHint().height())
    image = QImage(view.size(), QImage.Format.Format_ARGB32)
    view.render(image)

    def colour_at(x: float, row: int) -> QColor:
        return image.pixelColor(int(x), int(MARGIN + row * ROW_HEIGHT + ROW_HEIGHT / 2))

    assert colour_at(LABEL_WIDTH + 20, 0) == colours[ItemState.OK]
    assert colour_at(LABEL_WIDTH + 110, 1) == colours[ItemState.INFO]  # 55 s into 100 s
    assert colour_at(LABEL_WIDTH + 110, 0) == colours[ItemState.OK]


def test_size_follows_the_rows(qtbot):
    view = TimelineView()
    qtbot.addWidget(view)
    assert view.sizeHint().height() == 0
    view.set_rows([TimelineRow(label="Ch 0", start_unix=T0, end_unix=T0 + 1)] * 3, 0.0)
    assert view.sizeHint().height() > 3 * ROW_HEIGHT
    view.clear()
    assert view.rows == ()
    assert view.span() is None
