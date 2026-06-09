"""Main frameless floating window."""

from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from codex_traffic_lights.animation.engine import LightAnimationEngine
from codex_traffic_lights.models import CodexStatus, EdgeState
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.sound_settings import sound_dir
from codex_traffic_lights.status_aggregator import (
    aggregate_display_text,
    aggregate_status,
    codex_sessions_only,
)
from codex_traffic_lights.widgets.header import HeaderWidget
from codex_traffic_lights.widgets.session_matrix import SessionMatrixWidget
from codex_traffic_lights.widgets.side_buttons import SideButtonsWidget
from codex_traffic_lights.widgets.sound_settings_panel import SoundSettingsPanel
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
EXPANDED_HEIGHT = 220
EXPANDED_GLOBAL_HEIGHT = 88
ANIMATION_DURATION_MS = 200
SNAP_THRESHOLD = 30
SNAP_SLIDE_MS = 150
DOCK_CONTRACT_MS = 300
DOCK_EXPAND_MS = 250
DOCK_AUTO_DELAY_MS = 3000
DOCK_COLLAPSE_DELAY_MS = 500
DOCKED_WIDTH = 52
DOCKED_HEIGHT = 24
DOCKED_LAMP_DIAMETER = 10
DOCKED_BODY_RADIUS = 6
COMPACT_BODY_RADIUS = 16


class InstrumentPanel(QWidget):
    """Paint the floating hardware-panel body."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a paintable panel with adjustable corner radius."""
        super().__init__(parent)
        self._corner_radius = COMPACT_BODY_RADIUS

    def set_corner_radius(self, radius: int) -> None:
        """Set the panel corner radius used by compact and docked modes."""
        self._corner_radius = radius
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint a rounded dark instrument housing."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(
            rect.x(),
            rect.y(),
            rect.width(),
            rect.height(),
            self._corner_radius,
            self._corner_radius,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(PANEL_COLOR))
        painter.drawPath(path)
        painter.setBrush(QColor(BODY_BACKGROUND_COLOR))
        inner_radius = max(0, self._corner_radius - 3)
        painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), inner_radius, inner_radius)
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
        self._edge_state = EdgeState.FREE
        self._snap_edge: str | None = None
        self._move_animation: QPropertyAnimation | None = None
        self._geometry_animation: QPropertyAnimation | None = None
        self._content_fade_animation: QPropertyAnimation | None = None
        self._current_status = CodexStatus.OFFLINE
        self._sessions: list[SessionStatus] = []
        self.expanded_content_mode = "sessions"
        self._hover_expanded_from_dock = False
        self._pre_expand_snap_edge: str | None = None
        self._dock_timer = QTimer(self)
        self._dock_timer.setSingleShot(True)
        self._dock_timer.timeout.connect(self._dock_now)
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._dock_now)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.header = HeaderWidget()
        self.traffic_light = TrafficLightWidget()
        self.status_bar = StatusBarWidget()
        self.session_matrix = SessionMatrixWidget()
        self.sound_settings_panel = SoundSettingsPanel(sound_dir())
        self.side_buttons = SideButtonsWidget()
        self.animation_engine = LightAnimationEngine(self.traffic_light)
        self._content_opacity_effect = QGraphicsOpacityEffect(self.session_matrix)
        self._content_opacity_effect.setOpacity(0.0)
        self.session_matrix.setGraphicsEffect(self._content_opacity_effect)

        self._body = InstrumentPanel()
        self._body.setObjectName("main_body")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self._body_layout.addWidget(self.header)
        self._body_layout.addWidget(self.traffic_light, 1)
        self._body_layout.addWidget(self.status_bar)

        self._expanded_status_stack = QWidget()
        self._expanded_status_stack.setObjectName("expanded_status_stack")
        self._expanded_status_stack.hide()
        self._expanded_status_layout = QVBoxLayout(self._expanded_status_stack)
        self._expanded_status_layout.setContentsMargins(0, 12, 0, 0)
        self._expanded_status_layout.setSpacing(0)

        self._divider = QFrame()
        self._divider.setFixedHeight(1)
        self._divider.setStyleSheet("background: #2A2A30; border: 0;")
        self._divider.hide()
        self.session_matrix.hide()
        self.sound_settings_panel.hide()
        self._body_layout.addWidget(self._expanded_status_stack)
        self._body_layout.addWidget(self._divider)
        self._body_layout.addWidget(self.session_matrix, 1)
        self._body_layout.addWidget(self.sound_settings_panel, 1)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._body)
        root_layout.addWidget(self.side_buttons)

        self.side_buttons.zoom_in.connect(self.zoom_in)
        self.side_buttons.zoom_out.connect(self.zoom_out)
        self.side_buttons.expand_requested.connect(self.toggle_sessions_panel)
        self.side_buttons.settings_requested.connect(self.open_sound_settings)

        self.set_status(CodexStatus.OFFLINE)
        self.set_window_scale(1.0)

    @property
    def edge_state(self) -> EdgeState:
        """Return the current edge snap visual state."""
        return self._edge_state

    @property
    def snap_edge(self) -> str | None:
        """Return the snapped edge, if any."""
        return self._snap_edge

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
        self._apply_content_scale()
        self._apply_size(animated=False)

    def toggle_expanded(self) -> None:
        """Toggle the expanded sessions frame for legacy affordances."""
        if self.is_expanded:
            self.collapse_expanded()
        else:
            self.show_sessions()

    def toggle_sessions_panel(self) -> None:
        """Toggle the sessions panel from the dedicated expand button."""
        if self.is_expanded and self.expanded_content_mode == "sessions":
            self.collapse_expanded()
        else:
            self.show_sessions()

    def show_sessions(self) -> None:
        """Open Expanded mode with the multi-session matrix."""
        self._set_expanded_mode("sessions")

    def open_sound_settings(self) -> None:
        """Toggle Expanded mode with the custom sound settings panel."""
        if self.is_expanded and self.expanded_content_mode == "sound_settings":
            self.collapse_expanded()
            return
        self._set_expanded_mode("sound_settings")

    def collapse_expanded(self) -> None:
        """Collapse Expanded mode back to the compact lamp."""
        if not self.is_expanded:
            return
        self.is_expanded = False
        self.header.setVisible(True)
        self._expanded_status_stack.hide()
        self._divider.hide()
        self.session_matrix.hide()
        self.sound_settings_panel.hide()
        self._move_global_status_to_compact_stack()
        self._content_opacity_effect.setOpacity(0.0)
        self.traffic_light.set_orientation("vertical")
        self.traffic_light.set_lamp_diameter(round(36 * self.window_scale))
        self.traffic_light.setMinimumSize(72, 120)
        self.traffic_light.setMaximumHeight(16777215)
        self.status_bar.set_compact_height(False)
        self._apply_content_scale()
        # Re-snap to the same edge we were at before expanding.
        snap_edge = self._pre_expand_snap_edge
        self._pre_expand_snap_edge = None
        if snap_edge is not None:
            self._snap_edge = snap_edge
        self._apply_size(animated=True)
        if snap_edge is not None:
            self._edge_state = EdgeState.SNAPPED
            self._snap_edge = snap_edge
            self._dock_timer.start(DOCK_AUTO_DELAY_MS)

    def _set_expanded_mode(self, mode: str) -> None:
        """Open Expanded mode and show the requested content panel."""
        # Preserve snap edge for edge-aligned positioning, then reset all edge
        # state inline so the dock→compact animation does not fight the
        # compact→expanded animation that follows.
        snap_edge = self._snap_edge
        self._pre_expand_snap_edge = snap_edge
        self._dock_timer.stop()
        self._collapse_timer.stop()
        self._edge_state = EdgeState.FREE
        self._snap_edge = None
        self._hover_expanded_from_dock = False
        self._body.set_corner_radius(COMPACT_BODY_RADIUS)
        self.traffic_light.set_docked_mode(False)
        self.header.show()
        self.status_bar.show()
        self.side_buttons.show()

        was_expanded = self.is_expanded
        self.expanded_content_mode = mode
        self.is_expanded = True
        self.header.hide()
        self._expanded_status_stack.show()
        self._divider.show()
        if not was_expanded:
            self._move_global_status_to_expanded_stack()
            self.status_bar.set_compact_height(True)
        self._show_expanded_content(mode)
        self.traffic_light.setFixedHeight(EXPANDED_GLOBAL_HEIGHT - 42)
        self.traffic_light.set_orientation("horizontal")
        self.traffic_light.set_lamp_diameter(round(30 * self.window_scale))
        self._apply_content_scale()
        # Temporarily restore snap edge so _apply_size positions the expanded
        # window flush with the screen edge instead of expanding in-place.
        self._snap_edge = snap_edge
        self._apply_size(animated=not was_expanded)
        self._snap_edge = None

    def _show_expanded_content(self, mode: str) -> None:
        """Switch the visible Expanded content panel."""
        show_sessions = mode == "sessions"
        self.session_matrix.setVisible(show_sessions)
        self.sound_settings_panel.setVisible(not show_sessions)
        if show_sessions:
            self._start_content_fade(0.0, 1.0)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Collapse expanded mode with Escape."""
        if event.key() == Qt.Key_Escape and self.is_expanded:
            self.toggle_expanded()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Toggle expanded mode when the lamp area is double-clicked."""
        if event.button() == Qt.LeftButton and self._is_lamp_hit(event.pos()):
            self.toggle_expanded()
            event.accept()
            return
        if self._edge_state is EdgeState.SNAPPED:
            self._dock_now()
            event.accept()

    def _is_lamp_hit(self, pos: QPoint) -> bool:
        """Return whether a local point should use the lamp double-click action."""
        if self._edge_state is EdgeState.DOCKED:
            return self.rect().contains(pos)
        body_width = self._body.width()
        if body_width <= 0:
            body_width = round(
                (EXPANDED_BODY_WIDTH if self.is_expanded else BASE_BODY_WIDTH)
                * self.window_scale
            )
        if not QRect(0, 0, body_width, self.height()).contains(pos):
            return False
        return self.traffic_light.geometry().contains(pos)

    def _apply_size(self, animated: bool) -> None:
        """Apply compact or expanded dimensions for the current scale."""
        if self._edge_state is EdgeState.DOCKED:
            width, height = self._scaled_docked_size()
            self._body.setFixedWidth(width)
            target = QRect(
                self._aligned_x_for_width(width),
                self._clamped_y_for_height(height),
                width,
                height,
            )
            if animated and self.isVisible():
                self._animate_geometry(target, DOCK_CONTRACT_MS)
            else:
                self.resize(width, height)
                self.move(target.topLeft())
            return
        body_width = EXPANDED_BODY_WIDTH if self.is_expanded else BASE_BODY_WIDTH
        height_base = EXPANDED_HEIGHT if self.is_expanded else BASE_HEIGHT
        total_width = round((body_width + BASE_BUTTON_WIDTH) * self.window_scale)
        height = round(height_base * self.window_scale)
        self._body.setFixedWidth(round(body_width * self.window_scale))
        x = self._aligned_x_for_width(total_width) if self._snap_edge is not None else self.x()
        y = self._clamped_y_for_height(height) if self._snap_edge is not None else self.y()
        target = QRect(x, y, total_width, height)
        if animated and self.isVisible():
            self._animate_geometry(target)
        else:
            self.setGeometry(target)

    def _apply_content_scale(self) -> None:
        """Scale inner controls along with the frameless window shell."""
        self.header.set_scale(self.window_scale)
        self.status_bar.set_scale(self.window_scale)
        self.side_buttons.set_scale(self.window_scale)
        self.session_matrix.set_scale(self.window_scale)
        self.sound_settings_panel.set_scale(self.window_scale)
        if self._edge_state is EdgeState.DOCKED:
            width, height = self._scaled_docked_size()
            self.traffic_light.set_docked_mode(True)
            self.traffic_light.set_lamp_diameter(self._scaled_docked_lamp_diameter())
            self.traffic_light.setMinimumSize(width, height)
            self.traffic_light.setFixedSize(width, height)
            self._body.setFixedWidth(width)
            return
        self.traffic_light.set_docked_mode(False)
        if self.is_expanded:
            self.traffic_light.set_orientation("horizontal")
            self.traffic_light.set_lamp_diameter(round(30 * self.window_scale))
            expanded_lamp_height = round((EXPANDED_GLOBAL_HEIGHT - 42) * self.window_scale)
            self._expanded_status_stack.setFixedHeight(
                round(EXPANDED_GLOBAL_HEIGHT * self.window_scale)
            )
            self._expanded_status_layout.setContentsMargins(
                0,
                round(12 * self.window_scale),
                0,
                0,
            )
            self._expanded_status_layout.setSpacing(0)
            self.traffic_light.setFixedHeight(expanded_lamp_height)
            self.traffic_light.setFixedWidth(round(EXPANDED_BODY_WIDTH * self.window_scale))
        else:
            self.traffic_light.set_orientation("vertical")
            self.traffic_light.set_lamp_diameter(round(36 * self.window_scale))
            self.traffic_light.setMaximumSize(16777215, 16777215)
            self.traffic_light.setMinimumSize(
                round(BASE_BODY_WIDTH * self.window_scale),
                round(120 * self.window_scale),
            )

    def _move_global_status_to_expanded_stack(self) -> None:
        """Place global lamps above secondary status text in expanded mode."""
        self._body_layout.removeWidget(self.traffic_light)
        self._body_layout.removeWidget(self.status_bar)
        self._expanded_status_layout.addWidget(self.traffic_light, 1)
        self._expanded_status_layout.addWidget(self.status_bar, 0)

    def _move_global_status_to_compact_stack(self) -> None:
        """Restore global lamps and text to the compact vertical stack."""
        self._expanded_status_layout.removeWidget(self.traffic_light)
        self._expanded_status_layout.removeWidget(self.status_bar)
        self._body_layout.insertWidget(1, self.traffic_light, 1)
        self._body_layout.insertWidget(2, self.status_bar)

    def _start_content_fade(self, start: float, end: float) -> None:
        """Fade expanded content in as the panel slides open."""
        self._content_opacity_effect.setOpacity(start)
        self._content_fade_animation = QPropertyAnimation(
            self._content_opacity_effect,
            b"opacity",
            self,
        )
        self._content_fade_animation.setDuration(ANIMATION_DURATION_MS)
        self._content_fade_animation.setStartValue(start)
        self._content_fade_animation.setEndValue(end)
        self._content_fade_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._content_fade_animation.start()

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
        """Finish dragging and apply edge snapping when close to a side."""
        if event.button() == Qt.LeftButton:
            self._drag_origin = None
            self._apply_edge_snap()
            event.accept()

    def enterEvent(self, event: object) -> None:  # noqa: N802
        """Expand the docked mini indicator when the pointer enters it."""
        del event
        if self._edge_state is EdgeState.DOCKED:
            self._expand_from_dock()
        else:
            self._collapse_timer.stop()

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        """Schedule docked collapse after a hover-expanded window is left."""
        del event
        if self._hover_expanded_from_dock and self._edge_state is EdgeState.SNAPPED:
            self._schedule_dock_collapse()

    def _apply_edge_snap(self) -> bool:
        """Snap to the current screen's left or right edge when close enough."""
        if self.is_expanded:
            self._clear_edge_state()
            return False

        geometry = self._current_screen_geometry()
        edge = self._edge_for_current_position(geometry)
        if edge is None:
            if self._edge_state is EdgeState.DOCKED:
                self._expand_from_dock(animated=False)
            self._clear_edge_state()
            return False

        self._edge_state = EdgeState.SNAPPED
        self._snap_edge = edge
        self._hover_expanded_from_dock = False
        self._collapse_timer.stop()
        self._body.set_corner_radius(COMPACT_BODY_RADIUS)
        self.header.show()
        self.status_bar.show()
        self.side_buttons.show()
        self.traffic_light.set_docked_mode(False)
        self._apply_content_scale()
        self._apply_size(animated=False)
        self._align_to_snap_edge(SNAP_SLIDE_MS)
        self._dock_timer.start(DOCK_AUTO_DELAY_MS)
        return True

    def _dock_now(self) -> None:
        """Contract a snapped window into the visible mini LED indicator."""
        if self._snap_edge is None or self.is_expanded:
            return
        self._dock_timer.stop()
        self._collapse_timer.stop()
        self._hover_expanded_from_dock = False
        self._edge_state = EdgeState.DOCKED
        self.header.hide()
        self.status_bar.hide()
        self.side_buttons.hide()
        self._expanded_status_stack.hide()
        self._divider.hide()
        self.session_matrix.hide()
        self.sound_settings_panel.hide()
        self._body.set_corner_radius(self._scaled_docked_body_radius())
        self.traffic_light.set_docked_mode(True)
        self._apply_content_scale()
        self._apply_size(animated=True)

    def _expand_from_dock(self, animated: bool = True) -> None:
        """Restore a docked mini indicator to the full compact snapped shape."""
        if self._edge_state is not EdgeState.DOCKED:
            return
        self._collapse_timer.stop()
        self._edge_state = EdgeState.SNAPPED
        self._hover_expanded_from_dock = True
        self._body.set_corner_radius(COMPACT_BODY_RADIUS)
        self.header.show()
        self.status_bar.show()
        self.side_buttons.show()
        self.traffic_light.set_docked_mode(False)
        self._apply_content_scale()
        self._apply_size(animated=animated)
        self._align_to_snap_edge(DOCK_EXPAND_MS if animated else 0)

    def _scaled_docked_size(self) -> tuple[int, int]:
        """Return docked mini indicator size for the current window scale."""
        return (
            max(1, round(DOCKED_WIDTH * self.window_scale)),
            max(1, round(DOCKED_HEIGHT * self.window_scale)),
        )

    def _scaled_docked_lamp_diameter(self) -> int:
        """Return docked lamp diameter for the current window scale."""
        return max(1, round(DOCKED_LAMP_DIAMETER * self.window_scale))

    def _scaled_docked_body_radius(self) -> int:
        """Return docked panel radius for the current window scale."""
        return max(1, round(DOCKED_BODY_RADIUS * self.window_scale))

    def _schedule_dock_collapse(self) -> None:
        """Collapse a hover-expanded snapped window after a short delay."""
        if self._edge_state is EdgeState.SNAPPED and self._snap_edge is not None:
            self._dock_timer.stop()
            self._collapse_timer.start(DOCK_COLLAPSE_DELAY_MS)

    def _clear_edge_state(self) -> None:
        """Return edge behavior to free-floating mode without moving the window."""
        self._dock_timer.stop()
        self._collapse_timer.stop()
        self._edge_state = EdgeState.FREE
        self._snap_edge = None
        self._hover_expanded_from_dock = False
        self._body.set_corner_radius(COMPACT_BODY_RADIUS)
        self.traffic_light.set_docked_mode(False)
        self.header.show()
        self.status_bar.show()
        self.side_buttons.show()

    def _current_screen_geometry(self) -> QRect:
        """Return the available geometry of the screen containing this window."""
        screen = self.screen()
        if screen is None:
            return QRect(self.x(), self.y(), self.width(), self.height())
        return screen.availableGeometry()

    def _edge_for_current_position(self, geometry: QRect) -> str | None:
        """Return the nearest snap edge when the window is within threshold.

        Positive distance means the window edge is inside the screen; negative
        means it has been dragged past the screen edge.  Both cases trigger a
        snap so that partially-off-screen drops still lock to the edge.
        """
        left_distance = self.x() - geometry.left()
        right_distance = geometry.right() - (self.x() + self.width() - 1)
        candidates: list[tuple[int, str]] = []
        if left_distance <= SNAP_THRESHOLD:
            candidates.append((max(0, left_distance), "left"))
        if right_distance <= SNAP_THRESHOLD:
            candidates.append((max(0, right_distance), "right"))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def _align_to_snap_edge(self, duration_ms: int) -> None:
        """Align the current window width to the recorded snap edge."""
        if self._snap_edge is None:
            return
        point = QPoint(
            self._aligned_x_for_width(self.width()),
            self._clamped_y_for_height(self.height()),
        )
        self._animate_move(point, duration_ms)

    def _aligned_x_for_width(self, width: int) -> int:
        """Return the x coordinate that keeps a width aligned to the snap edge."""
        geometry = self._current_screen_geometry()
        if self._snap_edge == "left":
            return geometry.left()
        if self._snap_edge == "right":
            return geometry.right() - width + 1
        return self.x()

    def _clamped_y_for_height(self, height: int) -> int:
        """Return a y coordinate clamped inside the current screen."""
        geometry = self._current_screen_geometry()
        min_y = geometry.top()
        max_y = geometry.bottom() - height + 1
        return min(max(self.y(), min_y), max_y)

    def _animate_move(self, target: QPoint, duration_ms: int = ANIMATION_DURATION_MS) -> None:
        """Animate the window to a new position."""
        if not self.isVisible() or duration_ms <= 0:
            self.move(target)
            return
        self._move_animation = QPropertyAnimation(self, b"pos", self)
        self._move_animation.setDuration(duration_ms)
        self._move_animation.setStartValue(self.pos())
        self._move_animation.setEndValue(target)
        self._move_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._move_animation.start()

    def _animate_geometry(
        self,
        target: QRect,
        duration_ms: int = ANIMATION_DURATION_MS,
    ) -> None:
        """Animate the window geometry for compact/expanded transitions."""
        if not self.isVisible() or duration_ms <= 0:
            self.setGeometry(target)
            return
        self._geometry_animation = QPropertyAnimation(self, b"geometry", self)
        self._geometry_animation.setDuration(duration_ms)
        self._geometry_animation.setStartValue(self.geometry())
        self._geometry_animation.setEndValue(target)
        self._geometry_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._geometry_animation.start()
