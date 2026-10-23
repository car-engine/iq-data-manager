"""A thin frame around a dropdown, drawn in a colour while the field is marked (D95).

A style sheet on a QComboBox makes Qt draw it with its own generic look in place of
the Windows 11 one. MarkFrame leaves the dropdown without a style sheet: it holds the
dropdown with a margin of WIDTH pixels and paints the coloured frame in that margin.
The margin stays when the frame is off, so the layout does not move.
"""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget

WIDTH = 2  # pixels, as the frame of a marked text field


class MarkFrame(QWidget):
    """Holds one field and draws a frame around it in colour(), when it has one."""

    def __init__(self, field: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.field = field
        self._colour: QColor | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(WIDTH, WIDTH, WIDTH, WIDTH)
        layout.setSpacing(0)
        layout.addWidget(field)

    def colour(self) -> QColor | None:
        return self._colour

    def set_colour(self, colour: QColor | None) -> None:
        """The frame's colour, or None for no frame."""
        if colour != self._colour:
            self._colour = colour
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802  (Qt override)
        if self._colour is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self._colour, WIDTH))
        half = WIDTH / 2
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(half, half, -half, -half), 3, 3)
        painter.end()
