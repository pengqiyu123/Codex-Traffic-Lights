"""Tests for system tray behavior."""

from __future__ import annotations

from typing import Any

import pytest
from PyQt5.QtWidgets import QApplication, QWidget, QSystemTrayIcon

from codex_traffic_lights.tray import TrayIcon


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure tray tests have a QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_tray_icon_builds_required_context_menu() -> None:
    """TrayIcon should expose the required right-click menu actions."""
    window = QWidget()
    tray = TrayIcon(window)
    menu = tray.contextMenu()

    assert menu is not None
    labels = [
        "<separator>" if action.isSeparator() else action.text()
        for action in menu.actions()
    ]
    assert labels == ["显示主窗口", "隐藏", "<separator>", "退出"]


def test_tray_menu_actions_show_and_hide_main_window() -> None:
    """Show and hide menu actions should control the floating window."""
    window = QWidget()
    tray = TrayIcon(window)
    actions = tray.contextMenu().actions()

    actions[0].trigger()
    assert window.isVisible() is True

    actions[1].trigger()
    assert window.isVisible() is False


def test_tray_double_click_toggles_main_window() -> None:
    """Double-clicking the tray icon should toggle the floating window."""
    window = QWidget()
    tray = TrayIcon(window)

    tray._handle_activated(QSystemTrayIcon.DoubleClick)
    assert window.isVisible() is True

    tray._handle_activated(QSystemTrayIcon.DoubleClick)
    assert window.isVisible() is False


def test_show_message_delegates_to_qsystemtray_message() -> None:
    """show_message should delegate to QSystemTrayIcon.showMessage."""

    class RecordingTrayIcon(TrayIcon):
        def __init__(self, window: QWidget) -> None:
            self.messages: list[tuple[Any, ...]] = []
            super().__init__(window)

        def showMessage(self, *args: Any) -> None:  # noqa: N802
            self.messages.append(args)

    window = QWidget()
    tray = RecordingTrayIcon(window)

    tray.show_message("状态变化", "等待用户输入")

    assert tray.messages == [
        ("状态变化", "等待用户输入", QSystemTrayIcon.Information, 3000)
    ]
