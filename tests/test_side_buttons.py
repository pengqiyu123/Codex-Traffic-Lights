"""Tests for side buttons and main-window scaling."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QPixmap
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
        ("expand_button", "expand_requested"),
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


@pytest.mark.parametrize(
    "button_name",
    [
        "expand_button",
        "zoom_out_button",
        "zoom_in_button",
        "settings_button",
        "power_button",
        "sound_button",
    ],
)
def test_side_buttons_use_painted_icons_not_text(button_name: str) -> None:
    """Side buttons should be icon-painted controls, not emoji/text buttons."""
    widget = SideButtonsWidget()
    button = widget.findChild(QPushButton, button_name)

    assert button is not None
    assert button.text() == ""
    assert button.property("icon_name")
    assert button.styleSheet() == ""


def test_side_buttons_render_without_error() -> None:
    """Painted side buttons should render into a pixmap without crashing."""
    widget = SideButtonsWidget()
    widget.resize(32, 220)
    pixmap = QPixmap(widget.size())

    widget.render(pixmap)

    assert pixmap.size() == QSize(32, 220)


def test_expand_button_reuses_hidden_notification_slot() -> None:
    """The first side slot should now open sessions instead of showing notifications."""
    widget = SideButtonsWidget()

    assert not widget.expand_button.isHidden()
    assert widget.expand_button.property("icon_name") == "expand"
    assert widget.expand_button.toolTip() == "展开"
    assert widget.settings_button.toolTip() == "声音设置"


def test_side_buttons_scale_buttons_and_icon_area() -> None:
    """Zoom should resize side controls and their painted icon area."""
    widget = SideButtonsWidget()
    button = widget.zoom_in_button
    default_size = button.size()
    default_icon_extent = button.icon_extent

    widget.set_scale(2.0)

    assert button.width() > default_size.width()
    assert button.height() > default_size.height()
    assert button.icon_extent > default_icon_extent


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
