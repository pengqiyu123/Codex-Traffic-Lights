"""Tests for edge snapping and docked mini indicator mode."""

from __future__ import annotations

from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.models import EdgeState
from codex_traffic_lights.widgets.main_window import (
    DOCKED_HEIGHT,
    DOCKED_LAMP_DIAMETER,
    DOCKED_WIDTH,
    SNAP_THRESHOLD,
    FramelessMainWindow,
)
from codex_traffic_lights.widgets.traffic_light import TrafficLightWidget


class FakeScreen:
    """Small fake screen exposing availableGeometry like QScreen."""

    def __init__(self, geometry: QRect) -> None:
        self._geometry = geometry

    def availableGeometry(self) -> QRect:  # noqa: N802
        return self._geometry


def test_snap_triggers_within_threshold(qapp: QApplication) -> None:
    """Releasing within the snap threshold should align to the current screen edge."""
    window = _window_on_screen(QRect(100, 0, 500, 400))
    window.resize(104, 220)
    window.move(118, 40)

    snapped = window._apply_edge_snap()

    assert snapped is True
    assert window.edge_state is EdgeState.SNAPPED
    assert window.snap_edge == "left"
    assert window.x() == 100
    assert window._dock_timer.isActive()


def test_snap_does_not_trigger_outside_threshold(qapp: QApplication) -> None:
    """Releasing away from both edges should leave the window free."""
    window = _window_on_screen(QRect(100, 0, 500, 400))
    window.resize(104, 220)
    window.move(150, 40)

    snapped = window._apply_edge_snap()

    assert snapped is False
    assert window.edge_state is EdgeState.FREE
    assert window.snap_edge is None


def test_snap_blocked_in_expanded_mode(qapp: QApplication) -> None:
    """Expanded mode should not snap to edges."""
    window = _window_on_screen(QRect(0, 0, 500, 400))
    window.show_sessions()
    window.move(0, 20)

    snapped = window._apply_edge_snap()

    assert snapped is False
    assert window.edge_state is EdgeState.FREE


def test_snap_uses_current_screen_not_primary(qapp: QApplication) -> None:
    """Snapping should use the window's screen geometry."""
    window = _window_on_screen(QRect(200, 0, 400, 400))
    window.resize(104, 220)
    window.move(202, 30)

    window._apply_edge_snap()

    assert window.x() == 200
    assert window.snap_edge == "left"


def test_auto_dock_after_timeout(qapp: QApplication) -> None:
    """A snapped window should contract to the mini indicator on timeout."""
    window = _window_on_screen(QRect(0, 0, 500, 400))
    window.resize(104, 220)
    window.move(0, 40)
    window._apply_edge_snap()

    window._dock_timer.timeout.emit()

    assert window.edge_state is EdgeState.DOCKED
    assert window.width() == DOCKED_WIDTH
    assert window.height() == DOCKED_HEIGHT
    assert window.traffic_light.lamp_diameter == DOCKED_LAMP_DIAMETER
    assert window.traffic_light.is_docked_mode is True
    assert window.header.isHidden()
    assert window.status_bar.isHidden()
    assert window.side_buttons.isHidden()


def test_docking_on_right_edge_keeps_indicator_aligned(qapp: QApplication) -> None:
    """Right-edge docking should calculate the final x from the docked width."""
    window = _window_on_screen(QRect(0, 0, 500, 400))
    window.resize(104, 220)
    window.move(396, 40)
    window._apply_edge_snap()

    window._dock_now()

    assert window.edge_state is EdgeState.DOCKED
    assert window.x() == 500 - DOCKED_WIDTH


def test_visible_right_edge_dock_animation_targets_aligned_indicator(
    qapp: QApplication,
) -> None:
    """Visible right-edge dock animation should end with the mini strip on-screen."""
    window = _window_on_screen(QRect(0, 0, 500, 400))
    window.resize(104, 220)
    window.move(396, 40)
    window.isVisible = lambda: True  # type: ignore[method-assign]
    window._apply_edge_snap()

    window._dock_now()

    target = window._geometry_animation.endValue()
    assert target.x() == 500 - DOCKED_WIDTH
    assert target.width() == DOCKED_WIDTH


def test_visible_right_edge_hover_expand_targets_aligned_compact_window(
    qapp: QApplication,
) -> None:
    """Visible right-edge hover expansion should stay aligned to the screen edge."""
    window = _window_on_screen(QRect(0, 0, 500, 400))
    window.resize(104, 220)
    window.move(396, 40)
    window.isVisible = lambda: True  # type: ignore[method-assign]
    window._apply_edge_snap()
    window._dock_now()
    window._geometry_animation.stop()
    window.setGeometry(500 - DOCKED_WIDTH, 40, DOCKED_WIDTH, DOCKED_HEIGHT)

    window._expand_from_dock()

    target = window._geometry_animation.endValue()
    assert target.x() == 500 - 104
    assert target.width() == 104


def test_double_click_skips_dock_delay(qapp: QApplication) -> None:
    """Double-clicking a snapped compact window should dock immediately."""
    window = _window_on_screen(QRect(0, 0, 500, 400))
    window.resize(104, 220)
    window.move(0, 40)
    window._apply_edge_snap()

    window._dock_now()

    assert window.edge_state is EdgeState.DOCKED
    assert not window._dock_timer.isActive()


def test_hover_expands_docked(qapp: QApplication) -> None:
    """Hovering over the docked indicator should restore the full compact shape."""
    window = _docked_window()

    window._expand_from_dock()

    assert window.edge_state is EdgeState.SNAPPED
    assert window.width() == 104
    assert window.height() == 220
    assert window.traffic_light.lamp_diameter == 36
    assert window.traffic_light.is_docked_mode is False
    assert not window.header.isHidden()
    assert not window.status_bar.isHidden()
    assert not window.side_buttons.isHidden()


def test_leave_collapses_expanded(qapp: QApplication) -> None:
    """Leaving a hover-expanded snapped window should schedule docked collapse."""
    window = _docked_window()
    window._expand_from_dock()

    window._schedule_dock_collapse()

    assert window._collapse_timer.isActive()
    window._collapse_timer.timeout.emit()
    assert window.edge_state is EdgeState.DOCKED


def test_drag_away_unsnaps(qapp: QApplication) -> None:
    """Dragging a snapped window away from the edge should return it to FREE."""
    window = _window_on_screen(QRect(0, 0, 500, 400))
    window.resize(104, 220)
    window.move(0, 40)
    window._apply_edge_snap()
    window.move(SNAP_THRESHOLD + 20, 40)

    snapped = window._apply_edge_snap()

    assert snapped is False
    assert window.edge_state is EdgeState.FREE
    assert window.snap_edge is None


def test_snap_triggers_when_partially_off_screen_left(qapp: QApplication) -> None:
    """A window dragged past the left edge should still snap back to it."""
    window = _window_on_screen(QRect(100, 0, 500, 400))
    window.resize(104, 220)
    window.move(50, 40)  # left edge at x=50, well past screen left=100

    snapped = window._apply_edge_snap()

    assert snapped is True
    assert window.edge_state is EdgeState.SNAPPED
    assert window.snap_edge == "left"
    assert window.x() == 100


def test_snap_triggers_when_partially_off_screen_right(qapp: QApplication) -> None:
    """A window dragged past the right edge should still snap back to it."""
    screen = QRect(0, 0, 500, 400)
    window = _window_on_screen(screen)
    window.resize(104, 220)
    window.move(450, 40)  # right edge at 554, past screen right=499

    snapped = window._apply_edge_snap()

    assert snapped is True
    assert window.edge_state is EdgeState.SNAPPED
    assert window.snap_edge == "right"
    assert window.x() == screen.right() - 104 + 1


def test_docked_lamp_renders_simplified(qapp: QApplication) -> None:
    """The traffic-light widget should expose the simplified docked renderer mode."""
    widget = TrafficLightWidget()

    widget.set_docked_mode(True)

    assert widget.is_docked_mode is True
    assert widget.lamp_diameter == DOCKED_LAMP_DIAMETER


def _window_on_screen(geometry: QRect) -> FramelessMainWindow:
    window = FramelessMainWindow()
    window.screen = lambda: FakeScreen(geometry)  # type: ignore[method-assign]
    return window


def _docked_window() -> FramelessMainWindow:
    window = _window_on_screen(QRect(0, 0, 500, 400))
    window.resize(104, 220)
    window.move(0, 40)
    window._apply_edge_snap()
    window._dock_now()
    return window
