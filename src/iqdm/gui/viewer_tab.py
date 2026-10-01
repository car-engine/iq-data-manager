"""Viewer tab: browse and filter recordings, channels and RF chain details."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ViewerTab(QWidget):
    """Placeholder until Milestone 4."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        label = QLabel("Viewer: not implemented yet (Milestone 4)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
