"""Main frameless floating window."""

from __future__ import annotations

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from codex_traffic_lights.animation.engine import LightAnimationEngine
from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.widgets.header import HeaderWidget
from codex_traffic_lights.widgets.side_buttons import SideButtonsWidget
from codex_traffic_lights.widgets.status_bar import StatusBarWidget
from codex_traffic_lights.widgets.traffic_light import TrafficLightWidget

MIN_SCALE = 0.5
MAX_SCALE = 2.0
SCALE_STEP = 0.1
BASE_BODY_WIDTH = 80
BASE_BUTTON_WIDTH = 32
BASE_HEIGHT = 240
EDGE_THRESHOLD = 8
EDGE_VISIBLE_WIDTH = 12


class FramelessMainWindow(QWidget):
    """Frameless always-on-top window containing the traffic-light UI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create and compose the floating window."""
        super().__init__(parent)
        self.window_scale = 1.0
        self._drag_origin: QPoint | None = None
        self._hidden_edge: str | None = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.header = HeaderWidget()
        self.traffic_light = TrafficLightWidget()
        self.status_bar = StatusBarWidget()
        self.side_buttons = SideButtonsWidget()
        self.animation_engine = LightAnimationEngine(self.traffic_light)

        self._body = QWidget()
        self._body.setObjectName("main_body")
        self._body.setStyleSheet(
            """
            QWidget#main_body {
                background: #1A1A1A;
                border-radius: 12px;
            }
            """
        )
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.header)
        body_layout.addWidget(self.traffic_light, 1)
        body_layout.addWidget(self.status_bar)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._body)
        root_layout.addWidget(self.side_buttons)

        self.side_buttons.zoom_in.connect(self.zoom_in)
        self.side_buttons.zoom_out.connect(self.zoom_out)

        self.set_status(CodexStatus.OFFLINE)
        self.set_window_scale(1.0)

    def set_status(self, status: CodexStatus) -> None:
        """Update status text and light animation from a product status."""
        self.status_bar.set_status_text(status.label)
        self.animation_engine.set_status(status)

    def zoom_in(self) -> None:
        """Increase window scale by one step."""
        self.set_window_scale(self.window_scale + SCALE_STEP)

    def zoom_out(self) -> None:
        """Decrease window scale by one step."""
        self.set_window_scale(self.window_scale - SCALE_STEP)

    def set_window_scale(self, scale: float) -> None:
        """Set window scale while clamping to the supported 50%-200% range."""
        self.window_scale = round(max(MIN_SCALE, min(MAX_SCALE, scale)), 2)
        total_width = round((BASE_BODY_WIDTH + BASE_BUTTON_WIDTH) * self.window_scale)
        height = round(BASE_HEIGHT * self.window_scale)
        self._body.setFixedWidth(round(BASE_BODY_WIDTH * self.window_scale))
        self.side_buttons.setFixedWidth(round(BASE_BUTTON_WIDTH * self.window_scale))
        self.resize(total_width, height)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Remember the drag origin when the body is pressed."""
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Drag the window while the left mouse button is held."""
        if self._drag_origin is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_origin)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Finish dragging and apply edge hiding when close to a side."""
        if event.button() == Qt.LeftButton:
            self._drag_origin = None
            self._apply_edge_hide()
            event.accept()

    def enterEvent(self, event: object) -> None:  # noqa: N802
        """Reveal a half-hidden window when the pointer enters it."""
        del event
        self._reveal_from_edge()

    def _apply_edge_hide(self) -> None:
        """Hide most of the window when it is dropped near a screen edge."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        if self.x() <= geometry.left() + EDGE_THRESHOLD:
            self._hidden_edge = "left"
            self.move(geometry.left() - self.width() + EDGE_VISIBLE_WIDTH, self.y())
        elif self.x() + self.width() >= geometry.right() - EDGE_THRESHOLD:
            self._hidden_edge = "right"
            self.move(geometry.right() - EDGE_VISIBLE_WIDTH, self.y())
        else:
            self._hidden_edge = None

    def _reveal_from_edge(self) -> None:
        """Move a half-hidden window back into view."""
        if self._hidden_edge is None:
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        if self._hidden_edge == "left":
            self.move(geometry.left(), self.y())
        elif self._hidden_edge == "right":
            self.move(geometry.right() - self.width(), self.y())
        self._hidden_edge = None
