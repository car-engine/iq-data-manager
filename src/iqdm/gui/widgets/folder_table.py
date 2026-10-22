"""The folder table of the Log tab's "Several folders" mode (DECISIONS.md D90).

A view only: the Log tab gives it one FolderRow per folder and listens for the
current row and the tick boxes. Rows are found by the folder's key, so the current
row stays when the rows are set again.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from iqdm.entry import ItemState
from iqdm.gui.widgets.checklist import MARKS, colours_for

KEY_ROLE = Qt.ItemDataRole.UserRole


def folder_headers(zone: str) -> tuple[str, ...]:
    return (
        "Save",
        "Folder",
        f"Start ({zone})",
        f"End ({zone})",
        "Ch",
        "fc (MHz)",
        "Band",
        "fs",
        "Sample type",
        "Files",
        "Size",
        "State",
    )


TICK_COLUMN = 0
STATE_COLUMN = 11


@dataclass(frozen=True, kw_only=True)
class FolderRow:
    """The text of one row. state gives the mark and colour of the State column."""

    key: int
    ticked: bool
    can_tick: bool
    folder: str
    folder_tooltip: str
    start: str
    end: str
    channels: str
    fc: str
    band: str
    fs: str
    dtype: str
    files: str
    size: str
    state: ItemState
    state_text: str


class FolderTable(QTableWidget):
    """One row per folder, with a tick box for "save this folder"."""

    current_changed = Signal(object)  # the folder's key, or None
    tick_changed = Signal(int, bool)  # key, ticked

    def __init__(self, zone: str, parent: QWidget | None = None) -> None:
        super().__init__(0, len(folder_headers(zone)), parent)
        self.set_zone(zone)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._rows: tuple[FolderRow, ...] = ()
        self._filling = False
        self.itemSelectionChanged.connect(self._selection_changed)
        self.itemChanged.connect(self._item_changed)

    def set_zone(self, zone: str) -> None:
        self.setHorizontalHeaderLabels(folder_headers(zone))

    @property
    def rows(self) -> tuple[FolderRow, ...]:
        return self._rows

    def current_key(self) -> int | None:
        row = self.currentRow()
        if not 0 <= row < len(self._rows) or not self.selectionModel().selectedRows():
            return None
        return self._rows[row].key

    def select_key(self, key: int | None) -> None:
        for position, r in enumerate(self._rows):
            if r.key == key:
                self.selectRow(position)
                return
        self.clearSelection()

    def set_rows(self, rows: Sequence[FolderRow]) -> None:
        """Show these rows. The current row stays if its folder is still listed."""
        keep = self.current_key()
        self._filling = True
        self.blockSignals(True)
        try:
            self._rows = tuple(rows)
            self.setRowCount(len(self._rows))
            colours = colours_for(self.palette())
            for position, r in enumerate(self._rows):
                tick = QTableWidgetItem()
                flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                if r.can_tick:
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                tick.setFlags(flags)
                tick.setCheckState(Qt.CheckState.Checked if r.ticked else Qt.CheckState.Unchecked)
                tick.setData(KEY_ROLE, r.key)
                self.setItem(position, TICK_COLUMN, tick)
                texts = (
                    r.folder,
                    r.start,
                    r.end,
                    r.channels,
                    r.fc,
                    r.band,
                    r.fs,
                    r.dtype,
                    r.files,
                    r.size,
                    f"{MARKS[r.state]}  {r.state_text}",
                )
                for column, text in enumerate(texts, start=1):
                    item = QTableWidgetItem(text)
                    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    self.setItem(position, column, item)
                self.item(position, 1).setToolTip(r.folder_tooltip)
                state = self.item(position, STATE_COLUMN)
                state.setForeground(QBrush(colours[r.state]))
                state.setToolTip(r.state_text)
            self.select_key(keep)
        finally:
            self.blockSignals(False)
            self._filling = False
        if self.current_key() != keep:
            self.current_changed.emit(self.current_key())

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802  (Qt override)
        """Colour the State column again after a switch between light and dark."""
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self.set_rows(self._rows)
        super().changeEvent(event)

    def _selection_changed(self) -> None:
        if not self._filling:
            self.current_changed.emit(self.current_key())

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._filling or item.column() != TICK_COLUMN:
            return
        self.tick_changed.emit(item.data(KEY_ROLE), item.checkState() == Qt.CheckState.Checked)
