"""Tests for side buttons and main-window scaling."""

from __future__ import annotations

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication, QPushButton

from codex_traffic_lights.widgets.main_window import FramelessMainWindow
from codex_traffic_lights.widgets.side_buttons import SideButtonsWidget


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure widget tests have a QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.parametrize(
    ("button_name", "signal_name"),
    [
        ("notification_button", "notification_toggled"),
        ("zoom_out_button", "zoom_out"),
        ("zoom_in_button", "zoom_in"),
        ("settings_button", "settings_requested"),
        ("power_button", "power_toggled"),
        ("sound_button", "sound_toggled"),
    ],
)
def test_each_side_button_emits_its_signal(button_name: str, signal_name: str) -> None:
    """Each side button should emit the product action signal on click."""
    widget = SideButtonsWidget()
    button = widget.findChild(QPushButton, button_name)
    signal = getattr(widget, signal_name)
    spy = QSignalSpy(signal)

    assert button is not None
    button.click()

    assert len(spy) == 1


def test_main_window_zoom_buttons_clamp_scale_between_half_and_double() -> None:
    """Main-window zoom controls should clamp scale to 50%-200%."""
    window = FramelessMainWindow()
    zoom_out_button = window.side_buttons.findChild(QPushButton, "zoom_out_button")
    zoom_in_button = window.side_buttons.findChild(QPushButton, "zoom_in_button")

    assert zoom_out_button is not None
    assert zoom_in_button is not None

    for _ in range(20):
        zoom_out_button.click()
    assert window.window_scale == pytest.approx(0.5)

    for _ in range(40):
        zoom_in_button.click()
    assert window.window_scale == pytest.approx(2.0)
