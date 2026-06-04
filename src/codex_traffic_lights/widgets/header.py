"""Header widget that paints the Codex mark and title."""

from __future__ import annotations

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget

from codex_traffic_lights.widgets.codex_mark import paint_codex_mark, paint_codex_title


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

        icon_size = 28
        icon_rect = QRectF((self.width() - icon_size) / 2, 4, icon_size, icon_size)
        paint_codex_mark(painter, icon_rect)
        paint_codex_title(painter, QRectF(0, 31, self.width(), 15))
