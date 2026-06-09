"""System alert sound playback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.notification_policy import AlertKind
from codex_traffic_lights.sound_settings import resolve_sound_path


class SoundPlayer:
    """Play alert sounds for user-facing alert events."""

    def __init__(
        self,
        config: AppConfig | None = None,
        file_sound_fn: Callable[[Path], None] | None = None,
    ) -> None:
        """Create a sound player with an injectable backend for tests."""
        self._config = config or AppConfig()
        self._file_sound_fn = file_sound_fn or _default_file_sound_fn

    def set_config(self, config: AppConfig) -> None:
        """Update custom sound paths used for playback."""
        self._config = config

    def play(self, kind: AlertKind) -> None:
        """Play the appropriate sound for the given alert event."""
        try:
            self._file_sound_fn(resolve_sound_path(kind, self._config))
        except (OSError, RuntimeError):
            QApplication.beep()


_MEDIA_PLAYER: QMediaPlayer | None = None


def _default_file_sound_fn(path: Path) -> None:
    """Play a packaged MP3 sound through Qt multimedia."""
    global _MEDIA_PLAYER
    if _MEDIA_PLAYER is None:
        _MEDIA_PLAYER = QMediaPlayer()
    _MEDIA_PLAYER.setMedia(QMediaContent(QUrl.fromLocalFile(str(path))))
    _MEDIA_PLAYER.play()
