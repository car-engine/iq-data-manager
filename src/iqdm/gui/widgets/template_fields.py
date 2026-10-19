"""The dialog that asks which fields an exported template holds (DECISIONS.md D80)."""

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from iqdm.templates import TemplateField

TITLE = "Export template"
INTRO = "Choose the fields to save in the template. Empty fields start unticked."


class TemplateFieldsDialog(QDialog):
    """One tick box per field group, with the form's current value in its text."""

    def __init__(
        self,
        rows: Sequence[tuple[TemplateField, str, bool]],
        parent: QWidget | None = None,
    ) -> None:
        """rows: (field, text, ticked) in the order of the form."""
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.boxes: dict[TemplateField, QCheckBox] = {}
        layout = QVBoxLayout(self)
        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for field, text, ticked in rows:
            box = QCheckBox(text)
            box.setChecked(ticked)
            box.toggled.connect(self._update_ok)
            self.boxes[field] = box
            layout.addWidget(box)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save...")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_ok()

    def chosen(self) -> set[TemplateField]:
        return {field for field, box in self.boxes.items() if box.isChecked()}

    def _update_ok(self) -> None:
        """Save needs at least one ticked field."""
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.chosen()))
