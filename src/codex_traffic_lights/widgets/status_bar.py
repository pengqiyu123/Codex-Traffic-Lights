"""Status text widget for the current Codex product status."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from codex_traffic_lights.models import CodexStatus

DEFAULT_STATUS_COLOR = "#FF3B30"
BASE_FONT_SIZE = 10
BASE_MARGIN_LEFT = 4
BASE_MARGIN_TOP = 0
BASE_MARGIN_RIGHT = 4
BASE_MARGIN_BOTTOM = 8


class StatusBarWidget(QWidget):
    """Display the current user-facing Chinese status label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a compact status label area."""
        super().__init__(parent)
        self._label = QLabel(CodexStatus.OFFLINE.label)
        self._label.setObjectName("status_text_label")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        self._status_color = DEFAULT_STATUS_COLOR
        self._scale = 1.0
        self._layout = QVBoxLayout(self)
        self._layout.addWidget(self._label)
        self.set_scale(1.0)
        self._apply_label_style()

    @property
    def status_text(self) -> str:
        """Return the currently visible status text."""
        return self._label.text()

    def set_status_text(self, text: str) -> None:
        """Set the visible status text."""
        self._label.setText(text)

    def set_status_color(self, color: str) -> None:
        """Set the text color to match the active lamp."""
        self._status_color = color
        self._apply_label_style()

    def set_scale(self, scale: float) -> None:
        """Scale status text size and padding with the window."""
        self._scale = max(0.5, min(2.0, scale))
        font_size = max(7, round(BASE_FONT_SIZE * self._scale))
        font = QFont("Consolas", font_size, QFont.Bold)
        font.setFamilies(["Consolas", "JetBrains Mono", "Source Code Pro"])
        self._label.setFont(font)
        self._layout.setContentsMargins(
            round(BASE_MARGIN_LEFT * self._scale),
            round(BASE_MARGIN_TOP * self._scale),
            round(BASE_MARGIN_RIGHT * self._scale),
            round(BASE_MARGIN_BOTTOM * self._scale),
        )
        self._apply_label_style()

    def _apply_label_style(self) -> None:
        """Apply the minimal stylesheet needed for text color."""
        font_size = max(7, round(BASE_FONT_SIZE * self._scale))
        self._label.setStyleSheet(
            f"color: {self._status_color}; font-size: {font_size}px; "
            "font-weight: 600; background: transparent;"
        )
