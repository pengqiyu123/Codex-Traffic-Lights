"""Status text widget for the current Codex product status."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from codex_traffic_lights.models import CodexStatus

DEFAULT_STATUS_COLOR = "#FF3B30"
COMPACT_STATUS_FAMILIES = ["Consolas", "JetBrains Mono", "Source Code Pro"]
EXPANDED_STATUS_FAMILIES = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Segoe UI",
]
BASE_FONT_SIZE = 10
EXPANDED_FONT_SIZE_BONUS = 1
BASE_COMPACT_HEIGHT = 24
COMPACT_MARGIN_BOTTOM = 2
BASE_MARGIN_LEFT = 4
BASE_MARGIN_TOP = 0
BASE_MARGIN_RIGHT = 4
BASE_MARGIN_BOTTOM = 8
QWIDGETSIZE_MAX = 16_777_215


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
        self._compact_height = False
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
        self._apply_font()
        bottom_margin = COMPACT_MARGIN_BOTTOM if self._compact_height else BASE_MARGIN_BOTTOM
        self._layout.setContentsMargins(
            round(BASE_MARGIN_LEFT * self._scale),
            round(BASE_MARGIN_TOP * self._scale),
            round(BASE_MARGIN_RIGHT * self._scale),
            round(bottom_margin * self._scale),
        )
        self._apply_height_mode()
        self._apply_label_style()

    def set_compact_height(self, compact: bool) -> None:
        """Constrain status text height for the expanded instrument panel."""
        self._compact_height = compact
        self.set_scale(self._scale)
        self._apply_height_mode()

    def _font_size(self) -> int:
        """Return the scaled status font size for the current display mode."""
        bonus = EXPANDED_FONT_SIZE_BONUS if self._compact_height else 0
        return max(7, round(BASE_FONT_SIZE * self._scale) + bonus)

    def _font_weight(self) -> int:
        """Return a stronger status font weight in expanded mode."""
        return QFont.Black if self._compact_height else QFont.Bold

    def _apply_font(self) -> None:
        """Apply the current status text font."""
        families = (
            EXPANDED_STATUS_FAMILIES
            if self._compact_height
            else COMPACT_STATUS_FAMILIES
        )
        font = QFont(families[0])
        font.setFamilies(families)
        font.setPixelSize(self._font_size())
        font.setWeight(self._font_weight())
        self._label.setFont(font)

    def _apply_label_style(self) -> None:
        """Apply the minimal stylesheet needed for text color."""
        self._label.setStyleSheet(
            f"color: {self._status_color}; background: transparent;"
        )

    def _apply_height_mode(self) -> None:
        """Apply expanded compact height or restore default flexible sizing."""
        if self._compact_height:
            self.setFixedHeight(round(BASE_COMPACT_HEIGHT * self._scale))
            return
        self.setMinimumHeight(0)
        self.setMaximumHeight(QWIDGETSIZE_MAX)
