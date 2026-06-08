"""Session alert orchestration for tray notifications and sound."""

from __future__ import annotations

from PyQt5.QtCore import QObject

from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.notification_policy import compute_alerts
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.sound_player import SoundPlayer
from codex_traffic_lights.status_aggregator import codex_sessions_only
from codex_traffic_lights.tray import TrayIcon


class NotificationController(QObject):
    """Orchestrate session-based alerts via tray and sound."""

    def __init__(
        self,
        tray: TrayIcon,
        sound_player: SoundPlayer,
        parent: QObject | None = None,
    ) -> None:
        """Create an alert controller for session transitions."""
        super().__init__(parent)
        self._tray = tray
        self._sound_player = sound_player
        self._prev_status: dict[str, CodexStatus] = {}
        self._initialized = False
        self._notification_enabled = True
        self._sound_enabled = True

    def set_config(self, config: AppConfig) -> None:
        """Update runtime switches from application configuration."""
        self._notification_enabled = config.notification_enabled
        self._sound_enabled = config.sound_enabled

    def set_sessions(self, sessions: list[SessionStatus]) -> None:
        """Process the latest sessions and emit any user attention alerts."""
        codex_sessions = codex_sessions_only(list(sessions))
        alerts = compute_alerts(self._prev_status, codex_sessions, self._initialized)
        for alert in alerts:
            if self._sound_enabled:
                self._sound_player.play(alert.kind)

        self._prev_status = {
            session.session_key: session.status for session in codex_sessions
        }
        self._initialized = True
