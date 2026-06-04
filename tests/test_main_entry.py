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
        self.connected_slot: Any | None = None

    def connect(self, slot: Any) -> None:
        """Record the slot connected by application startup."""
        self.connected_slot = slot


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

    class FakeWindow:
        def __init__(self) -> None:
            self.shown = False
            self.statuses: list[CodexStatus] = []
            self.sessions: list[object] | None = None
            created["window"] = self

        def show(self) -> None:
            self.shown = True

        def set_status(self, status: CodexStatus) -> None:
            self.statuses.append(status)

        def set_sessions(self, sessions: list[object]) -> None:
            self.sessions = sessions

    class FakeTray:
        def __init__(self, window: FakeWindow) -> None:
            self.window = window
            self.shown = False
            created["tray"] = self

        def show(self) -> None:
            self.shown = True

    monkeypatch.setattr(entry, "QApplication", FakeApplication)
    monkeypatch.setattr(entry, "ConfigManager", FakeConfigManager)
    monkeypatch.setattr(entry, "ProcessMonitor", FakeMonitor)
    monkeypatch.setattr(entry, "HookFileWatcher", FakeHookWatcher)
    monkeypatch.setattr(entry, "FramelessMainWindow", FakeWindow)
    monkeypatch.setattr(entry, "TrayIcon", FakeTray)
    monkeypatch.setattr(entry.sys, "argv", ["codex-traffic-lights"])

    exit_code = entry.main()

    app = created["app"]
    monitor = created["monitor"]
    hook_watcher = created["hook_watcher"]
    window = created["window"]
    tray = created["tray"]
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
    assert window.shown is True
    assert tray.window is window
    assert tray.shown is True

    monitor.status_changed.connected_slot(CodexStatus.WAITING_APPROVAL)
    assert window.statuses == [CodexStatus.WAITING_APPROVAL]
    monitor.sessions_changed.connected_slot([])
    assert window.sessions == []

    hook_watcher.status_changed.connected_slot(CodexStatus.WORKING)
    assert monitor.registry_updates == 1


def test_entrypoint_file_stays_small() -> None:
    """Entry file should stay within the Task 6 size budget."""
    entry = import_entry_module()
    entry_path = Path(entry.__file__)

    assert len(entry_path.read_text(encoding="utf-8").splitlines()) <= 80
