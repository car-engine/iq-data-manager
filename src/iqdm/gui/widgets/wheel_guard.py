"""The mouse wheel never changes a dropdown or number field (DECISIONS.md D92).

Qt lets the wheel change a QComboBox or a spin box under the pointer. While the user
scrolls a long form, the pointer passes over such fields and changes them without
the user noticing. The filter below is installed once on the application. It keeps a
wheel event from each such field and leaves the event unaccepted, so Qt passes a
real wheel event on to the parent, and the page scrolls. An open dropdown list is a
separate widget, so the wheel still scrolls it.
"""

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox

GUARDED = (QComboBox, QAbstractSpinBox)


class WheelGuard(QObject):
    """An application event filter that keeps wheel events from the GUARDED fields."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802  (Qt override)
        if event.type() == QEvent.Type.Wheel and isinstance(watched, GUARDED):
            event.ignore()  # Qt passes an unaccepted real wheel event to the parent
            return True
        return False


def install(app: QApplication) -> WheelGuard:
    """Install the guard on `app` once and return it. A second call returns the first."""
    guard = app.findChild(WheelGuard)
    if guard is None:
        guard = WheelGuard(app)
        app.installEventFilter(guard)
    return guard
