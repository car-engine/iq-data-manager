"""Log recording tab: scan a recording folder and add it to the database."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class LogTab(QWidget):
    """Placeholder until Milestone 3."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        label = QLabel("Log recording: not implemented yet (Milestone 3)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
