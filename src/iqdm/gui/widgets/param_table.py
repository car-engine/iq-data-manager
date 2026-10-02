"""RF chain table of the Log tab: applies to, parameter, value, unit, remove."""

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from iqdm.entry import ParamInput

HEADERS = ("Applies to", "Parameter", "Value", "Unit", "")


@dataclass(eq=False)  # rows are found by identity
class _Row:
    applies_to: QComboBox
    param: QLineEdit
    value: QLineEdit
    unit: QLineEdit
    remove: QPushButton


class ParamTable(QWidget):
    """Editable RF chain rows. Parameter names autocomplete from set_param_names()."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._channels: list[int] = []
        self._rows: list[_Row] = []
        self._names = QStringListModel(self)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        self.add_button = QPushButton("Add row")
        self.add_button.clicked.connect(lambda: self.add_row())

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        layout.addLayout(buttons)

    # -- choices -----------------------------------------------------------

    def set_param_names(self, names: Sequence[str]) -> None:
        self._names.setStringList(list(names))

    def set_channels(self, indices: Sequence[int]) -> None:
        """Channels offered under "Applies to". A row keeps a channel that is gone,
        so the checklist can report it."""
        self._channels = list(indices)
        for row in self._rows:
            self._fill_applies_to(row.applies_to, row.applies_to.currentData())

    def _fill_applies_to(self, combo: QComboBox, selected: int | None) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Recording", None)
        indices = list(self._channels)
        if selected is not None and selected not in indices:
            indices.append(selected)
        for index in sorted(indices):
            combo.addItem(f"Ch {index}", index)
        combo.setCurrentIndex(max(combo.findData(selected), 0))
        combo.blockSignals(False)

    # -- rows --------------------------------------------------------------

    def add_row(self, param: ParamInput | None = None) -> None:
        p = param or ParamInput()
        applies_to = QComboBox()
        self._fill_applies_to(applies_to, p.channel_index)
        name = QLineEdit(p.param)
        completer = QCompleter(self._names, name)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        name.setCompleter(completer)
        row = _Row(
            applies_to=applies_to,
            param=name,
            value=QLineEdit(p.value),
            unit=QLineEdit(p.unit),
            remove=QPushButton("Remove"),
        )
        position = self.table.rowCount()
        self.table.insertRow(position)
        for col, widget in enumerate((row.applies_to, row.param, row.value, row.unit, row.remove)):
            self.table.setCellWidget(position, col, widget)
        applies_to.currentIndexChanged.connect(self.changed)
        for edit in (row.param, row.value, row.unit):
            edit.textChanged.connect(self.changed)
        row.remove.clicked.connect(lambda: self.remove_row(self._rows.index(row)))
        self._rows.append(row)
        self.changed.emit()

    def remove_row(self, position: int) -> None:
        self._rows.pop(position)
        self.table.removeRow(position)
        self.changed.emit()

    def set_rows(self, params: Sequence[ParamInput]) -> None:
        self.blockSignals(True)
        while self._rows:
            self.remove_row(len(self._rows) - 1)
        for p in params:
            self.add_row(p)
        self.blockSignals(False)
        self.changed.emit()

    def rows(self) -> list[ParamInput]:
        return [
            ParamInput(
                channel_index=r.applies_to.currentData(),
                param=r.param.text(),
                value=r.value.text(),
                unit=r.unit.text(),
            )
            for r in self._rows
        ]

    def row_widgets(self, position: int) -> tuple[QComboBox, QLineEdit, QLineEdit, QLineEdit]:
        """Widgets of one row, for tests and keyboard focus."""
        r = self._rows[position]
        return r.applies_to, r.param, r.value, r.unit
