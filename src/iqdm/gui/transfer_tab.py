"""Move / copy tab: archive recordings to the NAS or copy them to a local PC."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class TransferTab(QWidget):
    """Placeholder until Milestone 6."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        label = QLabel("Move / copy: not implemented yet (Milestone 6)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
