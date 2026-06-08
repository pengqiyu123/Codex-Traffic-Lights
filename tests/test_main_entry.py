"""Tests for the application entry point wiring."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

from codex_traffic_lights.models import AppConfig, CodexStatus


class FakeSignal:
    """Small signal stand-in that records a single connected slot."""

    def __init__(self) -> None:
        """Create an empty fake signal."""
        self.connected_slots: list[Any] = []

    def connect(self, slot: Any) -> None:
        """Record the slot connected by application startup."""
        self.connected_slots.append(slot)

    def emit(self, *args: object) -> None:
        """Invoke all recorded slots."""
        for slot in self.connected_slots:
            slot(*args)

    @property
    def connected_slot(self) -> Any | None:
        """Return the latest connected slot for compatibility with older tests."""
        return self.connected_slots[-1] if self.connected_slots else None


class FakeAboutToQuit:
    """Stand-in for QApplication.aboutToQuit."""

    def __init__(self) -> None:
        """Create an empty fake signal."""
        self.connected_slot: Any | None = None

    def connect(self, slot: Any) -> None:
        """Record the shutdown callback."""
        self.connected_slot = slot

    def emit(self) -> None:
        """Invoke the recorded shutdown callback."""
        if self.connected_slot is not None:
            self.connected_slot()


def import_entry_module() -> ModuleType:
    """Import the package entry module."""
    return importlib.import_module("codex_traffic_lights.__main__")


def test_main_wires_config_monitor_window_tray_and_exec(
    monkeypatch: object,
) -> None:
    """main should compose config, monitor, window, tray, signals, and event loop."""
    entry = import_entry_module()
    loaded_config = AppConfig(codex_process_name="codex-test")
    created: dict[str, Any] = {}

    class FakeApplication:
        def __init__(self, argv: list[str]) -> None:
            self.argv = argv
            self.application_name = ""
            self.organization_name = ""
            self.aboutToQuit = FakeAboutToQuit()
            created["app"] = self

        @staticmethod
        def instance() -> None:
            return None

        def setApplicationName(self, name: str) -> None:  # noqa: N802
            self.application_name = name

        def setOrganizationName(self, name: str) -> None:  # noqa: N802
            self.organization_name = name

        def exec(self) -> int:
            self.aboutToQuit.emit()
            return 23

    class FakeConfigManager:
        def load(self) -> AppConfig:
            created["config_loaded"] = True
            return loaded_config

        def save(self, config: AppConfig) -> None:
            created["saved_config"] = config

    class FakeMonitor:
        def __init__(self, config: AppConfig) -> None:
            self.config = config
            self.registry = object()
            self.status_changed = FakeSignal()
            self.sessions_changed = FakeSignal()
            self.started = False
            self.interrupted = False
            self.waited_ms: int | None = None
            self.registry_updates = 0
            created["monitor"] = self

        def start(self) -> None:
            self.started = True

        def apply_registry_update(self) -> None:
            self.registry_updates += 1

        def requestInterruption(self) -> None:  # noqa: N802
            self.interrupted = True

        def wait(self, timeout_ms: int) -> None:
            self.waited_ms = timeout_ms

    class FakeHookWatcher:
        def __init__(self, config: AppConfig, registry: object) -> None:
            self.config = config
            self.registry = registry
            self.status_changed = FakeSignal()
            self.started = False
            self.interrupted = False
            self.waited_ms: int | None = None
            created["hook_watcher"] = self

        def start(self) -> None:
            self.started = True

        def requestInterruption(self) -> None:  # noqa: N802
            self.interrupted = True

        def wait(self, timeout_ms: int) -> None:
            self.waited_ms = timeout_ms

    class FakeIpcConnector:
        def __init__(self, config: AppConfig, registry: object) -> None:
            self.config = config
            self.registry = registry
            self.status_changed = FakeSignal()
            self.sessions_changed = FakeSignal()
            self.started = False
            self.interrupted = False
            self.waited_ms: int | None = None
            created["ipc_connector"] = self

        def start(self) -> None:
            self.started = True

        def requestInterruption(self) -> None:  # noqa: N802
            self.interrupted = True

        def wait(self, timeout_ms: int) -> None:
            self.waited_ms = timeout_ms

    class FakeWindow:
        def __init__(self) -> None:
            self.shown = False
            self.statuses: list[CodexStatus] = []
            self.sessions: list[object] | None = None
            self.side_buttons = type(
                "FakeSideButtons",
                (),
                {
                    "power_toggled": FakeSignal(),
                    "notification_button": object(),
                    "sound_button": object(),
                },
            )()
            created["window"] = self

        def show(self) -> None:
            self.shown = True

        def hide(self) -> None:
            self.shown = False

        def raise_(self) -> None:
            created["window_raised"] = True

        def activateWindow(self) -> None:  # noqa: N802
            created["window_activated"] = True

        def set_status(self, status: CodexStatus) -> None:
            self.statuses.append(status)

        def set_sessions(self, sessions: list[object]) -> None:
            self.sessions = sessions

    class FakeTray:
        def __init__(self, window: FakeWindow) -> None:
            self.window = window
            self.shown = False
            self.messages: list[tuple[str, str]] = []
            created["tray"] = self

        def show(self) -> None:
            self.shown = True

        def show_message(self, title: str, text: str) -> None:
            self.messages.append((title, text))

    class FakeSoundPlayer:
        def __init__(self) -> None:
            created["sound_player"] = self

    class FakeNotificationController:
        def __init__(self, tray: FakeTray, sound_player: FakeSoundPlayer) -> None:
            self.tray = tray
            self.sound_player = sound_player
            self.configs: list[AppConfig] = []
            self.sessions: list[list[object]] = []
            created["notification_controller"] = self

        def set_config(self, config: AppConfig) -> None:
            self.configs.append(config)

        def set_sessions(self, sessions: list[object]) -> None:
            self.sessions.append(sessions)

    class FakeSettingsController:
        def __init__(
            self,
            config: AppConfig,
            config_manager: FakeConfigManager,
            notification_button: object,
            sound_button: object,
            on_config_changed: Any,
        ) -> None:
            self.config = config
            self.config_manager = config_manager
            self.notification_button = notification_button
            self.sound_button = sound_button
            self.on_config_changed = on_config_changed
            created["settings_controller"] = self

    monkeypatch.setattr(entry, "QApplication", FakeApplication)
    monkeypatch.setattr(entry, "ConfigManager", FakeConfigManager)
    monkeypatch.setattr(entry, "ProcessMonitor", FakeMonitor)
    monkeypatch.setattr(entry, "HookFileWatcher", FakeHookWatcher)
    monkeypatch.setattr(entry, "VSCodeIpcConnector", FakeIpcConnector)
    monkeypatch.setattr(entry, "FramelessMainWindow", FakeWindow)
    monkeypatch.setattr(entry, "TrayIcon", FakeTray)
    monkeypatch.setattr(entry, "SoundPlayer", FakeSoundPlayer)
    monkeypatch.setattr(entry, "NotificationController", FakeNotificationController)
    monkeypatch.setattr(entry, "SettingsController", FakeSettingsController)
    monkeypatch.setattr(entry.sys, "argv", ["codex-traffic-lights"])

    exit_code = entry.main()

    app = created["app"]
    monitor = created["monitor"]
    hook_watcher = created["hook_watcher"]
    ipc_connector = created["ipc_connector"]
    window = created["window"]
    tray = created["tray"]
    sound_player = created["sound_player"]
    notification_controller = created["notification_controller"]
    settings_controller = created["settings_controller"]
    assert exit_code == 23
    assert app.application_name == "Codex Traffic Lights"
    assert app.organization_name == "Codex Traffic Lights"
    assert created["config_loaded"] is True
    assert monitor.config is loaded_config
    assert monitor.started is True
    assert monitor.interrupted is True
    assert monitor.waited_ms == 1000
    assert hook_watcher.config is loaded_config
    assert hook_watcher.registry is monitor.registry
    assert hook_watcher.started is True
    assert hook_watcher.interrupted is True
    assert hook_watcher.waited_ms == 1000
    assert ipc_connector.config is loaded_config
    assert ipc_connector.registry is monitor.registry
    assert ipc_connector.started is True
    assert ipc_connector.interrupted is True
    assert ipc_connector.waited_ms == 1000
    assert window.shown is True
    assert tray.window is window
    assert tray.shown is True
    assert notification_controller.tray is tray
    assert notification_controller.sound_player is sound_player
    assert notification_controller.configs == [loaded_config]
    assert settings_controller.config is loaded_config
    assert settings_controller.notification_button is window.side_buttons.notification_button
    assert settings_controller.sound_button is window.side_buttons.sound_button

    monitor.status_changed.emit(CodexStatus.WAITING_APPROVAL)
    assert window.statuses == [CodexStatus.WAITING_APPROVAL]
    monitor.sessions_changed.emit([])
    assert window.sessions == []
    assert notification_controller.sessions == [[]]

    ipc_connector.status_changed.emit(CodexStatus.WORKING)
    assert window.statuses == [CodexStatus.WAITING_APPROVAL, CodexStatus.WORKING]
    ipc_connector.sessions_changed.emit(["ipc-session"])
    assert window.sessions == ["ipc-session"]
    assert notification_controller.sessions == [[], ["ipc-session"]]

    hook_watcher.status_changed.emit(CodexStatus.WORKING)
    assert monitor.registry_updates == 1

    settings_controller.on_config_changed(AppConfig(notification_enabled=False))
    assert notification_controller.configs[-1].notification_enabled is False


def test_entrypoint_keeps_feature_logic_in_dedicated_modules() -> None:
    """Entry file should compose controllers instead of owning feature logic."""
    entry = import_entry_module()
    entry_path = Path(entry.__file__)
    source = entry_path.read_text(encoding="utf-8")

    assert "compute_alerts" not in source
    assert "MessageBeep" not in source
    assert ".save(" not in source
