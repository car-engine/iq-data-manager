"""The mouse wheel never changes a dropdown or number field (DECISIONS.md D92).

Qt passes an unaccepted wheel event on to the parent only for real input. A test
sends its events itself, so these tests check that the field keeps its value and
leaves the event unaccepted. That the page then scrolls is a step of the manual test.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QListWidget,
    QSpinBox,
    QWidget,
)

from iqdm.app import MainWindow
from iqdm.gui.widgets import wheel_guard
from iqdm.gui.widgets.check_combo import CheckComboBox
from iqdm.gui.widgets.wheel_guard import WheelGuard


def wheel(widget: QWidget, steps: int = -1) -> QWheelEvent:
    """Send a wheel turn of `steps` notches to `widget`; negative turns toward the user."""
    centre = QPointF(widget.rect().center())
    event = QWheelEvent(
        centre,
        QPointF(widget.mapToGlobal(centre.toPoint())),
        QPoint(0, 0),
        QPoint(0, 120 * steps),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)
    return event


@pytest.fixture
def guarded(qapp) -> Iterator[WheelGuard]:
    yield wheel_guard.install(qapp)


@pytest.fixture
def unguarded(qapp) -> Iterator[None]:
    """No guard for the test; one installed earlier in the run comes back after it."""
    guard = qapp.findChild(WheelGuard)
    if guard is not None:
        qapp.removeEventFilter(guard)
    yield
    if guard is not None:
        qapp.installEventFilter(guard)


def combo(qtbot) -> QComboBox:
    box = QComboBox()
    box.addItems(["int16", "int8", "float32"])
    qtbot.addWidget(box)
    return box


def spin(qtbot) -> QSpinBox:
    box = QSpinBox()
    box.setRange(0, 100)
    box.setValue(50)
    qtbot.addWidget(box)
    return box


def test_without_the_guard_the_wheel_changes_the_fields(qtbot, unguarded):
    """The control case: Qt's own behaviour, which the guard stops."""
    box, number = combo(qtbot), spin(qtbot)
    wheel(box)
    wheel(number, steps=1)
    assert box.currentIndex() == 1
    assert number.value() == 51


def test_the_wheel_leaves_a_dropdown_unchanged(qtbot, guarded):
    box = combo(qtbot)
    event = wheel(box)
    assert box.currentIndex() == 0
    assert not event.isAccepted()  # so Qt passes it to the parent, which scrolls


def test_the_wheel_leaves_number_fields_unchanged(qtbot, guarded):
    number = spin(qtbot)
    decimal = QDoubleSpinBox()
    decimal.setValue(1.0)
    qtbot.addWidget(decimal)
    for _ in range(3):
        wheel(number, steps=1)
        wheel(decimal, steps=1)
    assert number.value() == 50
    assert decimal.value() == 1.0


def test_the_wheel_leaves_a_tick_box_list_unchanged(qtbot, guarded):
    box = CheckComboBox("All sites")
    qtbot.addWidget(box)
    box.set_items([("SiteA", 1), ("SiteB", 2)])
    before = box.currentIndex()
    wheel(box)
    assert box.currentIndex() == before


def test_other_widgets_still_get_the_wheel(qtbot, guarded):
    lines = QListWidget()
    lines.addItems([f"line {n}" for n in range(200)])
    lines.resize(200, 100)
    qtbot.addWidget(lines)
    lines.show()
    qtbot.waitExposed(lines)
    assert lines.verticalScrollBar().maximum() > 0
    assert guarded.eventFilter(lines.viewport(), wheel(lines.viewport())) is False
    assert lines.verticalScrollBar().value() > 0


def test_install_adds_one_guard(qapp):
    first = wheel_guard.install(qapp)
    assert wheel_guard.install(qapp) is first
    assert qapp.findChildren(WheelGuard) == [first]


def test_the_main_window_installs_the_guard(qtbot, qapp):
    earlier = qapp.findChild(WheelGuard)
    if earlier is not None:  # from an earlier test; the window installs its own
        qapp.removeEventFilter(earlier)
        earlier.setParent(None)
    window = MainWindow()
    qtbot.addWidget(window)
    assert qapp.findChild(WheelGuard) is not None
    sample_type = window.log_tab.dtype_combo
    before = sample_type.currentIndex()
    wheel(sample_type)
    assert sample_type.currentIndex() == before
