"""Main frameless floating window."""

from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt
from PyQt5.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from codex_traffic_lights.animation.engine import LightAnimationEngine
from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.status_aggregator import (
    aggregate_display_text,
    aggregate_status,
    codex_sessions_only,
)
from codex_traffic_lights.widgets.header import HeaderWidget
from codex_traffic_lights.widgets.session_matrix import SessionMatrixWidget
from codex_traffic_lights.widgets.side_buttons import SideButtonsWidget
from codex_traffic_lights.widgets.status_bar import StatusBarWidget
from codex_traffic_lights.widgets.traffic_light import (
    BODY_BACKGROUND_COLOR,
    BORDER_COLOR,
    PANEL_COLOR,
    STATUS_COLORS,
    TrafficLightWidget,
)

MIN_SCALE = 0.5
MAX_SCALE = 2.0
SCALE_STEP = 0.1
BASE_BODY_WIDTH = 72
BASE_BUTTON_WIDTH = 32
BASE_HEIGHT = 220
EXPANDED_BODY_WIDTH = 240
EXPANDED_HEIGHT = 292
EXPANDED_GLOBAL_HEIGHT = 144
EDGE_THRESHOLD = 8
EDGE_VISIBLE_WIDTH = 8
ANIMATION_DURATION_MS = 200

class InstrumentPanel(QWidget):
    """Paint the floating hardware-panel body."""

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint a rounded dark instrument housing."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 16, 16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(PANEL_COLOR))
        painter.drawPath(path)
        painter.setBrush(QColor(BODY_BACKGROUND_COLOR))
        painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 13, 13)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(BORDER_COLOR), 1))
        painter.drawPath(path)


class FramelessMainWindow(QWidget):
    """Frameless always-on-top window containing the traffic-light UI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create and compose the floating window."""
        super().__init__(parent)
        self.window_scale = 1.0
        self.is_expanded = False
        self._drag_origin: QPoint | None = None
        self._hidden_edge: str | None = None
        self._move_animation: QPropertyAnimation | None = None
        self._geometry_animation: QPropertyAnimation | None = None
        self._current_status = CodexStatus.OFFLINE
        self._sessions: list[SessionStatus] = []

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.header = HeaderWidget()
        self.traffic_light = TrafficLightWidget()
        self.status_bar = StatusBarWidget()
        self.session_matrix = SessionMatrixWidget()
        self.side_buttons = SideButtonsWidget()
        self.animation_engine = LightAnimationEngine(self.traffic_light)

        self._body = InstrumentPanel()
        self._body.setObjectName("main_body")
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.header)
        body_layout.addWidget(self.traffic_light, 1)
        body_layout.addWidget(self.status_bar)

        self._divider = QFrame()
        self._divider.setFixedHeight(1)
        self._divider.setStyleSheet("background: #2A2A30; border: 0;")
        self._divider.hide()
        self.session_matrix.hide()
        body_layout.addWidget(self._divider)
        body_layout.addWidget(self.session_matrix, 1)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._body)
        root_layout.addWidget(self.side_buttons)

        self.side_buttons.zoom_in.connect(self.zoom_in)
        self.side_buttons.zoom_out.connect(self.zoom_out)
        self.side_buttons.settings_requested.connect(self.toggle_expanded)

        self.set_status(CodexStatus.OFFLINE)
        self.set_window_scale(1.0)

    def set_status(self, status: CodexStatus) -> None:
        """Update status text and light animation from a product status."""
        self._current_status = status
        status_color = STATUS_COLORS[status]
        self.status_bar.set_status_text(aggregate_display_text(self._sessions, status))
        self.status_bar.set_status_color(status_color)
        self.side_buttons.set_accent_color(status_color)
        self.animation_engine.set_status(status)

    def set_sessions(self, sessions: list[SessionStatus]) -> None:
        """Update expanded matrix sessions and compact aggregate text."""
        self._sessions = codex_sessions_only(list(sessions))
        self.session_matrix.set_sessions(self._sessions)
        aggregate = aggregate_status(self._sessions)
        self.set_status(aggregate)

    def zoom_in(self) -> None:
        """Increase window scale by one step."""
        self.set_window_scale(self.window_scale + SCALE_STEP)

    def zoom_out(self) -> None:
        """Decrease window scale by one step."""
        self.set_window_scale(self.window_scale - SCALE_STEP)

    def set_window_scale(self, scale: float) -> None:
        """Set window scale while clamping to the supported 50%-200% range."""
        self.window_scale = round(max(MIN_SCALE, min(MAX_SCALE, scale)), 2)
        self._apply_size(animated=False)

    def toggle_expanded(self) -> None:
        """Toggle the expanded multi-session matrix frame."""
        self.is_expanded = not self.is_expanded
        self.header.setVisible(not self.is_expanded)
        self._divider.setVisible(self.is_expanded)
        self.session_matrix.setVisible(self.is_expanded)
        if self.is_expanded:
            self.traffic_light.setFixedHeight(EXPANDED_GLOBAL_HEIGHT - 42)
            self.traffic_light.set_lamp_diameter(22)
        else:
            self.traffic_light.set_lamp_diameter(None)
            self.traffic_light.setMinimumSize(72, 120)
            self.traffic_light.setMaximumHeight(16777215)
        self._apply_size(animated=True)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Collapse expanded mode with Escape."""
        if event.key() == Qt.Key_Escape and self.is_expanded:
            self.toggle_expanded()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Toggle expanded mode when the lamp area is double-clicked."""
        if event.button() == Qt.LeftButton and self.traffic_light.geometry().contains(event.pos()):
            self.toggle_expanded()
            event.accept()

    def _apply_size(self, animated: bool) -> None:
        """Apply compact or expanded dimensions for the current scale."""
        body_width = EXPANDED_BODY_WIDTH if self.is_expanded else BASE_BODY_WIDTH
        height_base = EXPANDED_HEIGHT if self.is_expanded else BASE_HEIGHT
        total_width = round((body_width + BASE_BUTTON_WIDTH) * self.window_scale)
        height = round(height_base * self.window_scale)
        self._body.setFixedWidth(round(body_width * self.window_scale))
        self.side_buttons.setFixedWidth(round(BASE_BUTTON_WIDTH * self.window_scale))
        if animated and self.isVisible():
            self._animate_geometry(QRect(self.x(), self.y(), total_width, height))
        else:
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
            target_x = geometry.left() - self.width() + EDGE_VISIBLE_WIDTH
            self._animate_move(QPoint(target_x, self.y()))
        elif self.x() + self.width() >= geometry.right() - EDGE_THRESHOLD:
            self._hidden_edge = "right"
            self._animate_move(QPoint(geometry.right() - EDGE_VISIBLE_WIDTH, self.y()))
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
            self._animate_move(QPoint(geometry.left(), self.y()))
        elif self._hidden_edge == "right":
            self._animate_move(QPoint(geometry.right() - self.width(), self.y()))
        self._hidden_edge = None

    def _animate_move(self, target: QPoint) -> None:
        """Animate the window to a new position."""
        if not self.isVisible():
            self.move(target)
            return
        self._move_animation = QPropertyAnimation(self, b"pos", self)
        self._move_animation.setDuration(ANIMATION_DURATION_MS)
        self._move_animation.setStartValue(self.pos())
        self._move_animation.setEndValue(target)
        self._move_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._move_animation.start()

    def _animate_geometry(self, target: QRect) -> None:
        """Animate the window geometry for compact/expanded transitions."""
        self._geometry_animation = QPropertyAnimation(self, b"geometry", self)
        self._geometry_animation.setDuration(ANIMATION_DURATION_MS)
        self._geometry_animation.setStartValue(self.geometry())
        self._geometry_animation.setEndValue(target)
        self._geometry_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._geometry_animation.start()
