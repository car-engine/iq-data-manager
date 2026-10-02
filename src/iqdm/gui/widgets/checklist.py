"""The "Before saving" checklist of the Log tab: one line per ChecklistItem."""

from collections.abc import Sequence

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from iqdm.entry import ChecklistItem, ItemState

MARKS = {
    ItemState.OK: "\N{CHECK MARK}",
    ItemState.INFO: "\N{CIRCLED LATIN SMALL LETTER I}",
    ItemState.TODO: "\N{WHITE CIRCLE}",
    ItemState.ERROR: "\N{BALLOT X}",
}
# Colours for a light background and for a dark one. Each keeps a contrast ratio of
# at least 4.5 against white and against #2d2d2d (Windows 11 dark fields).
LIGHT_COLOURS = {
    ItemState.OK: QColor(0, 120, 90),
    ItemState.INFO: QColor(150, 85, 0),
    ItemState.TODO: QColor(100, 100, 100),
    ItemState.ERROR: QColor(190, 0, 30),
}
DARK_COLOURS = {
    ItemState.OK: QColor(90, 210, 160),
    ItemState.INFO: QColor(245, 180, 80),
    ItemState.TODO: QColor(175, 175, 175),
    ItemState.ERROR: QColor(255, 120, 120),
}


def colours_for(palette: QPalette) -> dict[ItemState, QColor]:
    """The colour set that suits the palette's background."""
    dark = palette.color(QPalette.ColorRole.Base).lightnessF() < 0.5
    return DARK_COLOURS if dark else LIGHT_COLOURS


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
        self._show()

    def _show(self) -> None:
        colours = colours_for(self.palette())
        self.clear()
        for item in self._items:
            row = QListWidgetItem(f"{MARKS[item.state]}  {item.text}")
            row.setForeground(QBrush(colours[item.state]))
            self.addItem(row)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802  (Qt override)
        """Pick the colour set again after a switch between light and dark."""
        if event.type() == QEvent.Type.PaletteChange:
            self._show()
        super().changeEvent(event)
