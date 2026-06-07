"""Header widget that paints the Codex mark and title."""

from __future__ import annotations

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget

from codex_traffic_lights.widgets.codex_mark import paint_codex_mark, paint_codex_title

BASE_HEADER_HEIGHT = 50
BASE_ICON_SIZE = 28
BASE_ICON_TOP = 4
BASE_TITLE_TOP = 31
BASE_TITLE_HEIGHT = 15


class HeaderWidget(QWidget):
    """Draw the top Codex icon area and CODEX title."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a fixed-height header widget."""
        super().__init__(parent)
        self._scale = 1.0
        self.setFixedHeight(BASE_HEADER_HEIGHT)
        self.setMinimumWidth(72)

    def set_scale(self, scale: float) -> None:
        """Scale the header height and painted mark geometry."""
        self._scale = max(0.5, min(2.0, scale))
        self.setFixedHeight(round(BASE_HEADER_HEIGHT * self._scale))
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint the compact Codex mark and title."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        icon_size = BASE_ICON_SIZE * self._scale
        icon_rect = QRectF(
            (self.width() - icon_size) / 2,
            BASE_ICON_TOP * self._scale,
            icon_size,
            icon_size,
        )
        paint_codex_mark(painter, icon_rect)
        paint_codex_title(
            painter,
            QRectF(
                0,
                BASE_TITLE_TOP * self._scale,
                self.width(),
                BASE_TITLE_HEIGHT * self._scale,
            ),
        )
