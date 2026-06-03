"""Side action buttons for the floating window."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QWidget


class SideButtonsWidget(QWidget):
    """Vertical strip of compact action buttons."""

    notification_toggled = pyqtSignal(bool)
    zoom_in = pyqtSignal()
    zoom_out = pyqtSignal()
    settings_requested = pyqtSignal()
    power_toggled = pyqtSignal(bool)
    sound_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the six PRD-defined side buttons."""
        super().__init__(parent)
        self.setFixedWidth(32)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 18, 2, 18)
        layout.setSpacing(8)

        self.notification_button = self._make_button("🔔", "notification_button", True)
        self.zoom_out_button = self._make_button("−", "zoom_out_button")
        self.zoom_in_button = self._make_button("+", "zoom_in_button")
        self.settings_button = self._make_button("⋮", "settings_button")
        self.power_button = self._make_button("⏻", "power_button", True)
        self.sound_button = self._make_button("🔇", "sound_button", True)

        for button in [
            self.notification_button,
            self.zoom_out_button,
            self.zoom_in_button,
            self.settings_button,
            self.power_button,
            self.sound_button,
        ]:
            layout.addWidget(button)
        layout.addStretch(1)

        self.notification_button.toggled.connect(self.notification_toggled)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.settings_button.clicked.connect(self.settings_requested)
        self.power_button.toggled.connect(self.power_toggled)
        self.sound_button.toggled.connect(self.sound_toggled)

    def _make_button(
        self,
        text: str,
        object_name: str,
        checkable: bool = False,
    ) -> QPushButton:
        """Create a compact icon-like button."""
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setCheckable(checkable)
        button.setFixedSize(26, 26)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            """
            QPushButton {
                border: none;
                border-radius: 6px;
                color: rgba(255,255,255,0.55);
                background: rgba(255,255,255,0.10);
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton:hover {
                color: rgba(255,255,255,1.0);
                background: rgba(255,255,255,0.20);
            }
            QPushButton:checked {
                color: #FFD700;
                background: rgba(255,215,0,0.18);
            }
            """
        )
        return button
