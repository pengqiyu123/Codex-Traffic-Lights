"""Tests for settings toggle persistence."""

from __future__ import annotations

from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.settings_controller import SettingsController


class FakeSignal:
    """Minimal signal recorder for toggle callbacks."""

    def __init__(self) -> None:
        self.connected_slot: object | None = None

    def connect(self, slot: object) -> None:
        self.connected_slot = slot

    def emit(self, checked: bool) -> None:
        assert callable(self.connected_slot)
        self.connected_slot(checked)


class FakeButton:
    """Small checkable-button stand-in."""

    def __init__(self) -> None:
        self.checked = False
        self.toggled = FakeSignal()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        self.checked = checked

    def isChecked(self) -> bool:  # noqa: N802
        return self.checked


class FakeConfigManager:
    """Record saved configs."""

    def __init__(self) -> None:
        self.saved: list[AppConfig] = []

    def save(self, config: AppConfig) -> None:
        self.saved.append(config)


def test_settings_controller_initializes_button_polarity() -> None:
    """Bell uses direct polarity, mute uses inverse sound polarity."""
    notification_button = FakeButton()
    sound_button = FakeButton()

    SettingsController(
        AppConfig(notification_enabled=True, sound_enabled=False),
        FakeConfigManager(),
        notification_button,
        sound_button,
        lambda _config: None,
    )

    assert notification_button.isChecked() is True
    assert sound_button.isChecked() is True


def test_settings_controller_persists_notification_toggle() -> None:
    """Notification toggles should save config and notify the runtime."""
    manager = FakeConfigManager()
    notification_button = FakeButton()
    sound_button = FakeButton()
    changed: list[AppConfig] = []
    SettingsController(
        AppConfig(notification_enabled=True, sound_enabled=True),
        manager,
        notification_button,
        sound_button,
        changed.append,
    )

    notification_button.toggled.emit(False)

    assert manager.saved[-1].notification_enabled is False
    assert manager.saved[-1].sound_enabled is True
    assert changed[-1] == manager.saved[-1]


def test_settings_controller_persists_inverse_mute_toggle() -> None:
    """Checked mute means sound_enabled is false."""
    manager = FakeConfigManager()
    notification_button = FakeButton()
    sound_button = FakeButton()
    changed: list[AppConfig] = []
    SettingsController(
        AppConfig(notification_enabled=True, sound_enabled=True),
        manager,
        notification_button,
        sound_button,
        changed.append,
    )

    sound_button.toggled.emit(True)

    assert manager.saved[-1].sound_enabled is False
    assert manager.saved[-1].notification_enabled is True
    assert changed[-1] == manager.saved[-1]
