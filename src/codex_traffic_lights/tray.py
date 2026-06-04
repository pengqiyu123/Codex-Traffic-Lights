"""System tray integration for the floating traffic-light window."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QObject, QRectF, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QSystemTrayIcon, QWidget

from codex_traffic_lights.widgets.codex_mark import paint_codex_mark

ICON_PATH = Path(__file__).resolve().parent / "resources" / "icons" / "app.ico"


class TrayIcon(QSystemTrayIcon):
    """QSystemTrayIcon wrapper with the product menu and window toggle behavior."""

    def __init__(self, main_window: QWidget, parent: QObject | None = None) -> None:
        """Create a tray icon bound to the floating main window."""
        super().__init__(parent)
        self.main_window = main_window
        self.setIcon(_load_icon())
        self.setToolTip("Codex Traffic Lights")

        menu = QMenu()
        self.show_window_action = QAction("显示主窗口", self)
        self.hide_window_action = QAction("隐藏", self)
        self.quit_action = QAction("退出", self)

        self.show_window_action.triggered.connect(self._show_window)
        self.hide_window_action.triggered.connect(self._hide_window)
        self.quit_action.triggered.connect(self._quit_application)

        menu.addAction(self.show_window_action)
        menu.addAction(self.hide_window_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        self.setContextMenu(menu)
        self.activated.connect(self._handle_activated)

    def show_message(self, title: str, text: str) -> None:
        """Show a short tray notification bubble."""
        self.showMessage(title, text, QSystemTrayIcon.Information, 3000)

    def _handle_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Toggle the main window when the tray icon is double-clicked."""
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_window()

    def _show_window(self, _checked: bool = False) -> None:
        """Show and foreground the floating window."""
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _hide_window(self, _checked: bool = False) -> None:
        """Hide the floating window."""
        self.main_window.hide()

    def _toggle_window(self) -> None:
        """Toggle the floating window visibility."""
        if self.main_window.isVisible():
            self._hide_window()
        else:
            self._show_window()

    def _quit_application(self, _checked: bool = False) -> None:
        """Quit the running QApplication."""
        QApplication.quit()


def _load_icon() -> QIcon:
    """Load the packaged icon or create a small fallback icon."""
    icon = QIcon(str(ICON_PATH))
    if not icon.isNull():
        return icon

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    paint_codex_mark(painter, QRectF(2, 2, 28, 28), with_shadow=False)
    painter.end()
    return QIcon(pixmap)
