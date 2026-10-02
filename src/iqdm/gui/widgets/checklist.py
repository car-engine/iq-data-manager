"""The "Before saving" checklist of the Log tab: one line per ChecklistItem."""

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from iqdm.entry import ChecklistItem, ItemState

MARKS = {
    ItemState.OK: "\N{CHECK MARK}",
    ItemState.INFO: "\N{CIRCLED LATIN SMALL LETTER I}",
    ItemState.TODO: "\N{WHITE CIRCLE}",
    ItemState.ERROR: "\N{BALLOT X}",
}
COLOURS = {
    ItemState.OK: QColor(0, 120, 90),
    ItemState.INFO: QColor(170, 100, 0),
    ItemState.TODO: QColor(110, 110, 110),
    ItemState.ERROR: QColor(190, 0, 30),
}


class ChecklistView(QListWidget):
    """Read-only list of checklist items with a mark and a colour per state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._items: tuple[ChecklistItem, ...] = ()

    @property
    def items(self) -> tuple[ChecklistItem, ...]:
        return self._items

    def set_items(self, items: Sequence[ChecklistItem]) -> None:
        self._items = tuple(items)
        self.clear()
        for item in self._items:
            row = QListWidgetItem(f"{MARKS[item.state]}  {item.text}")
            row.setForeground(QBrush(COLOURS[item.state]))
            self.addItem(row)
