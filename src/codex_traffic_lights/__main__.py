from __future__ import annotations

import sys
from collections.abc import Sequence

from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.config import ConfigManager
from codex_traffic_lights.hook_bridge import HookFileWatcher
from codex_traffic_lights.hook_installer import HookInstaller
from codex_traffic_lights.process_monitor import ProcessMonitor
from codex_traffic_lights.tray import TrayIcon
from codex_traffic_lights.widgets.main_window import FramelessMainWindow


def main(argv: Sequence[str] | None = None) -> int:
    """Create the application, wire modules together, and run the event loop."""
    app = QApplication.instance() or QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("Codex Traffic Lights")
    app.setOrganizationName("Codex Traffic Lights")

    config = ConfigManager().load()
    _install_hooks(HookInstaller())
    monitor = ProcessMonitor(config)
    hook_watcher = HookFileWatcher(config, monitor.registry)
    window = FramelessMainWindow()
    tray = TrayIcon(window)

    monitor.status_changed.connect(window.set_status)
    monitor.sessions_changed.connect(window.set_sessions)
    hook_watcher.status_changed.connect(lambda _status: monitor.apply_registry_update())
    _connect_power_button(window, tray)
    app.aboutToQuit.connect(lambda: _stop_workers(monitor, hook_watcher))

    window.show()
    tray.show()
    hook_watcher.start()
    monitor.start()
    return app.exec()


def _install_hooks(installer: HookInstaller) -> None:
    """Install user-level hook bridge entries without blocking app startup."""
    try:
        installer.install_codex_hooks()
        installer.install_claude_hooks()
        print("[Codex Traffic Lights] Hooks installed successfully.")
    except Exception as exc:
        print(f"[Codex Traffic Lights] Hook install failed (non-fatal): {exc}")


def _connect_power_button(window: FramelessMainWindow, tray: TrayIcon) -> None:
    """Wire the power button to minimize to tray and restore the window."""
    side_buttons = getattr(window, "side_buttons", None)
    power_toggled = getattr(side_buttons, "power_toggled", None)
    if power_toggled is None:
        return

    def _on_power_toggled(checked: bool) -> None:
        if checked:
            window.hide()
            tray.show_message("Codex Traffic Lights", "已最小化到托盘，双击图标恢复")
        else:
            window.show()
            window.raise_()
            window.activateWindow()

    power_toggled.connect(_on_power_toggled)


def _stop_workers(monitor: ProcessMonitor, hook_watcher: HookFileWatcher) -> None:
    """Ask background workers to stop and wait briefly for shutdown."""
    monitor.requestInterruption()
    hook_watcher.requestInterruption()
    monitor.wait(1000)
    hook_watcher.wait(1000)


if __name__ == "__main__":
    raise SystemExit(main())
