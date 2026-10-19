"""A drop-down list with a tick box per entry (DECISIONS.md D78).

Nothing ticked means all: the closed box then shows `all_text`, such as "All sites".
Otherwise it shows the ticked names, separated by commas, and its tooltip lists them
one per line. A click on an entry ticks or unticks it and leaves the list open.
"""

from collections.abc import Iterable, Sequence

from PySide6.QtCore import QEvent, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QWidget,
)

DATA_ROLE = Qt.ItemDataRole.UserRole


class CheckComboBox(QComboBox):
    """Several choices from one list. `changed` is emitted when a tick changes."""

    changed = Signal()

    def __init__(self, all_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all_text = all_text
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._model.itemChanged.connect(self._item_changed)
        self.view().viewport().installEventFilter(self)
        self._update_summary()

    # ---------------------------------------------------------------------
    # Entries and ticks
    # ---------------------------------------------------------------------

    def set_items(self, items: Sequence[tuple[str, object]]) -> None:
        """Replace the entries with (text, data) pairs. Ticks stay on the same data."""
        keep = self.checked_data()
        self._model.blockSignals(True)
        self._model.clear()
        for text, data in items:
            item = QStandardItem(text)
            item.setData(data, DATA_ROLE)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            checked = data in keep
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self._model.appendRow(item)
        self._model.blockSignals(False)
        self._update_summary()
        if set(self.checked_data()) != set(keep):
            self.changed.emit()

    def items(self) -> list[str]:
        return [self._model.item(row).text() for row in range(self._model.rowCount())]

    def checked_data(self) -> list[object]:
        """The data of the ticked entries, in list order."""
        return [
            self._model.item(row).data(DATA_ROLE)
            for row in range(self._model.rowCount())
            if self._model.item(row).checkState() == Qt.CheckState.Checked
        ]

    def checked_texts(self) -> list[str]:
        return [
            self._model.item(row).text()
            for row in range(self._model.rowCount())
            if self._model.item(row).checkState() == Qt.CheckState.Checked
        ]

    def set_checked(self, data: Iterable[object]) -> None:
        """Tick exactly the entries whose data is in `data`."""
        wanted = list(data)
        self._model.blockSignals(True)
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            checked = item.data(DATA_ROLE) in wanted
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._model.blockSignals(False)
        self._update_summary()
        self.changed.emit()

    def clear_checks(self) -> None:
        self.set_checked(())

    def summary(self) -> str:
        """The text the closed box shows."""
        return self._summary

    # ---------------------------------------------------------------------
    # Behaviour
    # ---------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802  (Qt name)
        """A click on an entry toggles its tick and keeps the list open."""
        if watched is self.view().viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            index = self.view().indexAt(event.position().toPoint())
            if index.isValid():
                self._toggle(index)
            return True
        return super().eventFilter(watched, event)

    def _toggle(self, index: QModelIndex) -> None:
        item = self._model.itemFromIndex(index)
        checked = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)

    def _item_changed(self, _item: QStandardItem) -> None:
        self._update_summary()
        self.changed.emit()

    def _update_summary(self) -> None:
        texts = self.checked_texts()
        self._summary = ", ".join(texts) if texts else self._all_text
        self.setToolTip("\n".join(texts))
        self.update()

    def paintEvent(self, _event: QEvent) -> None:  # noqa: N802  (Qt name)
        """Draw the box with the summary in place of the current entry."""
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = self._summary
        option.currentIcon = QIcon()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)
