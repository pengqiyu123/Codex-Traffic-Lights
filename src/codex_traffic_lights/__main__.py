"""Application entry point for Codex Traffic Lights."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.config import ConfigManager
from codex_traffic_lights.hook_bridge import HookFileWatcher
from codex_traffic_lights.process_monitor import ProcessMonitor
from codex_traffic_lights.tray import TrayIcon
from codex_traffic_lights.widgets.main_window import FramelessMainWindow


def main(argv: Sequence[str] | None = None) -> int:
    """Create the application, wire modules together, and run the event loop."""
    arguments = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(arguments)
    app.setApplicationName("Codex Traffic Lights")
    app.setOrganizationName("Codex Traffic Lights")

    config = ConfigManager().load()
    monitor = ProcessMonitor(config)
    hook_watcher = HookFileWatcher(config, monitor.registry)
    window = FramelessMainWindow()
    tray = TrayIcon(window)

    monitor.status_changed.connect(window.set_status)
    monitor.sessions_changed.connect(window.set_sessions)
    hook_watcher.status_changed.connect(lambda _status: monitor.apply_registry_update())
    app.aboutToQuit.connect(lambda: _stop_workers(monitor, hook_watcher))

    window.show()
    tray.show()
    hook_watcher.start()
    monitor.start()
    return app.exec()


def _stop_workers(monitor: ProcessMonitor, hook_watcher: HookFileWatcher) -> None:
    """Ask background workers to stop and wait briefly for shutdown."""
    for worker in (monitor, hook_watcher):
        worker.requestInterruption()
        worker.wait(1000)


if __name__ == "__main__":
    raise SystemExit(main())
