"""Header widget that paints the Codex mark and title."""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget


class HeaderWidget(QWidget):
    """Draw the top Codex icon area and CODEX title."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a fixed-height header widget."""
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setMinimumWidth(80)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint the compact Codex mark and title."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        icon_rect = QRectF((self.width() - 38) / 2, 7, 38, 28)
        gradient = QLinearGradient(icon_rect.topLeft(), icon_rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#56D7FF"))
        gradient.setColorAt(1.0, QColor("#7A5CFF"))

        path = QPainterPath()
        path.addRoundedRect(icon_rect, 13, 13)
        path.addEllipse(QRectF(icon_rect.left() + 6, icon_rect.top() - 5, 16, 16))
        path.addEllipse(QRectF(icon_rect.left() + 17, icon_rect.top() - 8, 18, 18))
        painter.fillPath(path, gradient)

        painter.setPen(QPen(QColor("#FFFFFF")))
        prompt_font = QFont("Consolas", 10, QFont.Bold)
        painter.setFont(prompt_font)
        painter.drawText(icon_rect, Qt.AlignCenter, "_>_")

        title_font = QFont("Arial", 11, QFont.Bold)
        painter.setFont(title_font)
        painter.drawText(QRectF(0, 42, self.width(), 18), Qt.AlignCenter, "CODEX")
