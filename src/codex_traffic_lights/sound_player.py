"""System alert sound playback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.notification_policy import AlertKind

SOUND_FILE_BY_KIND = {
    AlertKind.COMPLETED: "completed.mp3",
    AlertKind.WAITING_APPROVAL: "waiting_approval.mp3",
    AlertKind.WAITING_USER_INPUT: "waiting_user_input.mp3",
    AlertKind.ERROR: "error.mp3",
}


class SoundPlayer:
    """Play packaged alert sounds for user-facing alert events."""

    def __init__(
        self,
        file_sound_fn: Callable[[Path], None] | None = None,
    ) -> None:
        """Create a sound player with an injectable backend for tests."""
        self._file_sound_fn = file_sound_fn or _default_file_sound_fn

    def play(self, kind: AlertKind) -> None:
        """Play the appropriate packaged sound for the given alert event."""
        try:
            self._file_sound_fn(_sound_path(SOUND_FILE_BY_KIND[kind]))
        except (OSError, RuntimeError):
            QApplication.beep()


def _sound_path(filename: str) -> Path:
    """Return the packaged sound asset path."""
    return Path(__file__).resolve().parent / "resources" / "sounds" / filename


_MEDIA_PLAYER: QMediaPlayer | None = None


def _default_file_sound_fn(path: Path) -> None:
    """Play a packaged MP3 sound through Qt multimedia."""
    global _MEDIA_PLAYER
    if _MEDIA_PLAYER is None:
        _MEDIA_PLAYER = QMediaPlayer()
    _MEDIA_PLAYER.setMedia(QMediaContent(QUrl.fromLocalFile(str(path))))
    _MEDIA_PLAYER.play()
