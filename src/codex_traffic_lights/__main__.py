"""Application entry point for Codex Traffic Lights."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.config import ConfigManager
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
    window = FramelessMainWindow()
    tray = TrayIcon(window)

    monitor.status_changed.connect(window.set_status)
    monitor.sessions_changed.connect(window.set_sessions)
    app.aboutToQuit.connect(lambda: _stop_monitor(monitor))

    window.show()
    tray.show()
    monitor.start()
    return app.exec()


def _stop_monitor(monitor: ProcessMonitor) -> None:
    """Ask the monitor thread to stop and wait briefly for shutdown."""
    monitor.requestInterruption()
    monitor.wait(1000)


if __name__ == "__main__":
    raise SystemExit(main())
