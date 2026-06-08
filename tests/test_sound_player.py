"""Tests for system alert sound playback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_traffic_lights.notification_policy import AlertKind
from codex_traffic_lights.sound_player import SOUND_FILE_BY_KIND, SoundPlayer


def test_sound_player_uses_local_mp3_assets_for_all_alerts() -> None:
    """Selected local MP3 assets should be used for every alert event."""
    file_calls: list[Path] = []
    player = SoundPlayer(file_sound_fn=file_calls.append)

    for kind in AlertKind:
        player.play(kind)

    assert [path.name for path in file_calls] == [
        SOUND_FILE_BY_KIND[kind] for kind in AlertKind
    ]


def test_selected_sound_assets_exist() -> None:
    """Packaged sound assets should be present in product resources."""
    resource_dir = Path("src/codex_traffic_lights/resources/sounds")

    for filename in SOUND_FILE_BY_KIND.values():
        assert (resource_dir / filename).is_file()


def test_sound_player_falls_back_to_qapplication_beep_on_sound_failure(
    monkeypatch: Any,
) -> None:
    """A failing OS sound call should fall back to QApplication.beep."""
    beeps: list[bool] = []

    def failing_sound(_path: Path) -> None:
        raise OSError("sound unavailable")

    class FakeApplication:
        @staticmethod
        def beep() -> None:
            beeps.append(True)

    monkeypatch.setattr("codex_traffic_lights.sound_player.QApplication", FakeApplication)

    SoundPlayer(file_sound_fn=failing_sound).play(AlertKind.ERROR)

    assert beeps == [True]
