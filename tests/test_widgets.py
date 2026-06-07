"""Tests for core UI widgets."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.animation.effects import STATUS_EFFECTS
from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.widgets.header import HeaderWidget
from codex_traffic_lights.widgets.main_window import FramelessMainWindow
from codex_traffic_lights.widgets.status_bar import StatusBarWidget
from codex_traffic_lights.widgets.traffic_light import (
    BODY_BACKGROUND_COLOR,
    LAMP_PALETTE,
    PANEL_COLOR,
    TrafficLightWidget,
)


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure widget tests have a QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_header_widget_has_prd_fixed_height() -> None:
    """Header should reserve the compact 50px instrument title area."""
    header = HeaderWidget()

    assert header.minimumHeight() == 50
    assert header.maximumHeight() == 50


def test_header_widget_renders_without_error() -> None:
    """Header painting should render into a pixmap without crashing."""
    header = HeaderWidget()
    header.resize(72, 50)
    pixmap = QPixmap(header.size())

    header.render(pixmap)

    assert pixmap.size() == QSize(72, 50)


def test_traffic_light_palette_matches_industrial_spec() -> None:
    """Traffic-light rendering should use the industrial instrument palette."""
    assert BODY_BACKGROUND_COLOR == "#0D0D0F"
    assert PANEL_COLOR == "#16161A"
    for palette in LAMP_PALETTE.values():
        assert _relative_luminance(palette.bright) - _relative_luminance(palette.dim) > 100
        assert _relative_luminance(palette.dim) < 24


def test_traffic_light_widget_accepts_three_opacity_values() -> None:
    """TrafficLightWidget should expose red/yellow/green opacity properties."""
    widget = TrafficLightWidget()

    widget.set_light_opacity(0.2, 0.4, 0.6)

    assert widget.red_opacity == pytest.approx(0.2)
    assert widget.yellow_opacity == pytest.approx(0.4)
    assert widget.green_opacity == pytest.approx(0.6)


def test_traffic_light_widget_accepts_indexed_animation_updates() -> None:
    """TrafficLightWidget should accept indexed updates from the animation engine."""
    widget = TrafficLightWidget()

    widget.set_light_effect(1, STATUS_EFFECTS[CodexStatus.WAITING_APPROVAL][1])
    widget.set_light_opacity(1, 0.75)

    assert widget.yellow_opacity == pytest.approx(0.75)


def test_traffic_light_widget_renders_without_error() -> None:
    """Traffic-light painting should render into a pixmap without crashing."""
    widget = TrafficLightWidget()
    widget.resize(80, 130)
    for light_index, effect in enumerate(STATUS_EFFECTS[CodexStatus.WAITING_APPROVAL]):
        widget.set_light_effect(light_index, effect)
    widget.set_light_opacity(0.1, 0.8, 0.8)
    pixmap = QPixmap(widget.size())

    widget.render(pixmap)

    assert pixmap.size() == QSize(80, 130)


def test_traffic_light_widget_can_render_horizontal_lamps() -> None:
    """Expanded mode should be able to render the global lamp row horizontally."""
    widget = TrafficLightWidget()

    widget.set_orientation("horizontal")
    widget.set_lamp_diameter(32)

    assert widget.orientation == "horizontal"
    assert widget.lamp_diameter == 32


def test_traffic_light_off_lamps_have_subtle_highlight() -> None:
    """Unlit lamps should stay visually dark instead of carrying a bright glass spot."""
    widget = TrafficLightWidget()
    widget.resize(80, 130)
    for light_index, effect in enumerate(STATUS_EFFECTS[CodexStatus.WORKING]):
        widget.set_light_effect(light_index, effect)
    widget.set_light_opacity(0.02, 1.0, 0.02)
    pixmap = QPixmap(widget.size())

    widget.render(pixmap)

    red_sample = pixmap.toImage().pixelColor(34, 21)
    yellow_sample = pixmap.toImage().pixelColor(34, 65)
    assert _color_luminance(yellow_sample.red(), yellow_sample.green(), yellow_sample.blue()) > (
        _color_luminance(red_sample.red(), red_sample.green(), red_sample.blue()) + 45
    )


def test_status_bar_sets_visible_status_text() -> None:
    """StatusBarWidget should expose the current user-facing text."""
    status_bar = StatusBarWidget()

    status_bar.set_status_text(CodexStatus.WAITING_USER_INPUT.label)

    assert status_bar.status_text == CodexStatus.WAITING_USER_INPUT.label


def test_status_bar_accepts_status_color() -> None:
    """Status bar text color should be updateable from the active status lamp."""
    status_bar = StatusBarWidget()

    status_bar.set_status_color("#34C759")

    assert "#34C759" in status_bar.findChild(type(status_bar._label)).styleSheet()


def test_main_window_set_status_uses_codex_status_label() -> None:
    """Main window should show product labels, not app-server internals."""
    window = FramelessMainWindow()

    window.set_status(CodexStatus.WAITING_APPROVAL)

    assert window.status_bar.status_text == CodexStatus.WAITING_APPROVAL.label


def test_main_window_uses_new_compact_dimensions() -> None:
    """Compact mode should use the 72x220 body size from the visual redesign."""
    window = FramelessMainWindow()
    window.show()

    assert window._body.width() == 72
    assert window.width() == 104
    assert window.height() == 220


def test_main_window_scale_updates_content_dimensions() -> None:
    """Zoom should scale the lamp body and side controls, not only the frame."""
    window = FramelessMainWindow()
    default_button = window.side_buttons.zoom_in_button.size()
    default_header_height = window.header.height()
    default_lamp_diameter = window.traffic_light.lamp_diameter

    window.set_window_scale(2.0)

    assert window.side_buttons.zoom_in_button.width() > default_button.width()
    assert window.side_buttons.zoom_in_button.height() > default_button.height()
    assert window.header.height() > default_header_height
    assert window.traffic_light.lamp_diameter > default_lamp_diameter


def test_main_window_toggles_expanded_frame() -> None:
    """The settings affordance should toggle the reserved expanded frame."""
    window = FramelessMainWindow()

    assert window.is_expanded is False

    window.toggle_expanded()

    assert window.is_expanded is True
    assert window.width() == 272
    assert window.height() <= 340
    assert window.traffic_light.orientation == "horizontal"

    window.toggle_expanded()

    assert window.is_expanded is False
    assert window.width() == 104
    assert window.height() == 220
    assert window.traffic_light.orientation == "vertical"


def test_main_window_filters_claude_sessions_from_display_and_aggregate() -> None:
    """Claude sessions should not appear in the Codex-only traffic light UI."""
    window = FramelessMainWindow()
    codex_session = _session("vscode-ipc", "codex-a", "codex", CodexStatus.WORKING)
    claude_session = _session("claude", "claude-a", "claude", CodexStatus.ERROR)

    window.set_sessions([claude_session, codex_session])

    assert window._sessions == [codex_session]
    assert window.status_bar.status_text == CodexStatus.WORKING.label
    assert [column.session for column in window.session_matrix.session_columns] == [codex_session]


def _relative_luminance(hex_color: str) -> float:
    color = hex_color.removeprefix("#")
    return _color_luminance(
        int(color[0:2], 16),
        int(color[2:4], 16),
        int(color[4:6], 16),
    )


def _color_luminance(red: int, green: int, blue: int) -> float:
    return red * 0.2126 + green * 0.7152 + blue * 0.0722


def _session(
    endpoint_id: str,
    thread_id: str,
    display_name: str,
    status: CodexStatus,
) -> SessionStatus:
    return SessionStatus(
        session_key=f"{endpoint_id}::{thread_id}",
        thread_id=thread_id,
        endpoint_id=endpoint_id,
        display_name=display_name,
        status=status,
        last_updated=100.0,
    )
