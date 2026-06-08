from __future__ import annotations

import sys
from collections.abc import Sequence

from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.config import ConfigManager
from codex_traffic_lights.hook_bridge import HookFileWatcher
from codex_traffic_lights.hook_installer import HookInstaller
from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.notification_controller import NotificationController
from codex_traffic_lights.process_monitor import ProcessMonitor
from codex_traffic_lights.settings_controller import SettingsController
from codex_traffic_lights.sound_player import SoundPlayer
from codex_traffic_lights.tray import TrayIcon
from codex_traffic_lights.tray import connect_power_button as _connect_power_button
from codex_traffic_lights.vscode_ipc import VSCodeIpcConnector
from codex_traffic_lights.widgets.main_window import FramelessMainWindow


def main(argv: Sequence[str] | None = None) -> int:
    """Create the application, wire modules together, and run the event loop."""
    app = QApplication.instance() or QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("Codex Traffic Lights")
    app.setOrganizationName("Codex Traffic Lights")

    config_manager = ConfigManager()
    config = config_manager.load()
    _install_hooks(HookInstaller())
    monitor = ProcessMonitor(config)
    hook_watcher = HookFileWatcher(config, monitor.registry)
    ipc_connector = VSCodeIpcConnector(config, monitor.registry)
    window = FramelessMainWindow()
    tray = TrayIcon(window)
    alerts, _settings = _connect_alerts(window, config, config_manager, tray)

    _connect_status_sources((monitor, ipc_connector), window, alerts)
    hook_watcher.status_changed.connect(lambda _status: monitor.apply_registry_update())
    _connect_power_button(window, tray)
    app.aboutToQuit.connect(lambda: _stop_workers(monitor, hook_watcher, ipc_connector))

    window.show()
    tray.show()
    for worker in (hook_watcher, ipc_connector, monitor):
        worker.start()
    return app.exec()


def _install_hooks(installer: HookInstaller) -> None:
    """Install user-level hook bridge entries without blocking app startup."""
    try:
        installer.install_codex_hooks()
        installer.install_claude_hooks()
        print("[Codex Traffic Lights] Hooks installed successfully.")
    except Exception as exc:
        print(f"[Codex Traffic Lights] Hook install failed (non-fatal): {exc}")


def _connect_status_sources(
    sources: Sequence[ProcessMonitor | VSCodeIpcConnector],
    window: FramelessMainWindow,
    alerts: NotificationController,
) -> None:
    """Wire status sources to the window and alert controller."""
    for source in sources:
        source.status_changed.connect(window.set_status)
        source.sessions_changed.connect(window.set_sessions)
        source.sessions_changed.connect(alerts.set_sessions)


def _connect_alerts(
    window: FramelessMainWindow,
    config: AppConfig,
    config_manager: ConfigManager,
    tray: TrayIcon,
) -> tuple[NotificationController, SettingsController]:
    """Wire notification, sound, and persistent setting controllers."""
    alerts = NotificationController(tray, SoundPlayer())
    alerts.set_config(config)
    side = window.side_buttons
    buttons = side.notification_button, side.sound_button
    settings = SettingsController(config, config_manager, *buttons, alerts.set_config)
    return alerts, settings


def _stop_workers(
    *workers: ProcessMonitor | HookFileWatcher | VSCodeIpcConnector,
) -> None:
    """Request worker shutdown and wait briefly for each thread."""
    for worker in workers:
        worker.requestInterruption()
    for worker in workers:
        worker.wait(1000)


if __name__ == "__main__":
    raise SystemExit(main())
