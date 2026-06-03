"""Tests for core UI widgets."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.animation.effects import STATUS_EFFECTS
from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.widgets.header import HeaderWidget
from codex_traffic_lights.widgets.main_window import FramelessMainWindow
from codex_traffic_lights.widgets.status_bar import StatusBarWidget
from codex_traffic_lights.widgets.traffic_light import TrafficLightWidget


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure widget tests have a QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_header_widget_has_prd_fixed_height() -> None:
    """Header should reserve the 70px icon and title area from the PRD."""
    header = HeaderWidget()

    assert header.minimumHeight() == 70
    assert header.maximumHeight() == 70


def test_header_widget_renders_without_error() -> None:
    """Header painting should render into a pixmap without crashing."""
    header = HeaderWidget()
    header.resize(80, 70)
    pixmap = QPixmap(header.size())

    header.render(pixmap)

    assert pixmap.size() == QSize(80, 70)


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


def test_status_bar_sets_visible_status_text() -> None:
    """StatusBarWidget should expose the current user-facing text."""
    status_bar = StatusBarWidget()

    status_bar.set_status_text(CodexStatus.WAITING_USER_INPUT.label)

    assert status_bar.status_text == CodexStatus.WAITING_USER_INPUT.label


def test_main_window_set_status_uses_codex_status_label() -> None:
    """Main window should show product labels, not app-server internals."""
    window = FramelessMainWindow()

    window.set_status(CodexStatus.WAITING_APPROVAL)

    assert window.status_bar.status_text == CodexStatus.WAITING_APPROVAL.label
