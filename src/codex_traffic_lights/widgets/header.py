"""Header widget that paints the Codex mark and title."""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget


class HeaderWidget(QWidget):
    """Draw the top Codex icon area and CODEX title."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a fixed-height header widget."""
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setMinimumWidth(72)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint the compact Codex mark and title."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        icon_rect = QRectF((self.width() - 16) / 2, 9, 16, 12)
        painter.setPen(QPen(QColor("#2A2A30"), 1))
        painter.setBrush(QColor("#12313A"))
        painter.drawRoundedRect(icon_rect.adjusted(-1, -1, 1, 1), 2, 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#56D7FF"))
        painter.drawRoundedRect(icon_rect, 1.5, 1.5)

        painter.setPen(QPen(QColor("#0D0D0F")))
        prompt_font = QFont("Consolas", 8, QFont.Bold)
        painter.setFont(prompt_font)
        painter.drawText(icon_rect.adjusted(0, -0.5, 0, 0), Qt.AlignCenter, ">_")

        title_font = QFont("Consolas", 10, QFont.Bold)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        painter.setFont(title_font)
        painter.setPen(QPen(QColor("#6A6A70")))
        painter.drawText(QRectF(0, 27, self.width(), 16), Qt.AlignCenter, "CODEX")
