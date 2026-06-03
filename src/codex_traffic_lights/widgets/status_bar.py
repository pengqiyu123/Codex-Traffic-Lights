"""Status text widget for the current Codex product status."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from codex_traffic_lights.models import CodexStatus

DEFAULT_STATUS_COLOR = "#FF3B30"


class StatusBarWidget(QWidget):
    """Display the current user-facing Chinese status label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a compact status label area."""
        super().__init__(parent)
        self._label = QLabel(CodexStatus.OFFLINE.label)
        self._label.setObjectName("status_text_label")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        font = QFont("Consolas", 10, QFont.Bold)
        font.setFamilies(["Consolas", "JetBrains Mono", "Source Code Pro"])
        self._label.setFont(font)
        self._status_color = DEFAULT_STATUS_COLOR
        self._apply_label_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 8)
        layout.addWidget(self._label)

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

    def _apply_label_style(self) -> None:
        """Apply the minimal stylesheet needed for text color."""
        self._label.setStyleSheet(
            f"color: {self._status_color}; font-size: 10px; "
            "font-weight: 600; background: transparent;"
        )
