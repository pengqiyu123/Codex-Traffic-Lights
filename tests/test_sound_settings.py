"""Tests for custom alert sound file settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.notification_policy import AlertKind
from codex_traffic_lights.sound_settings import (
    SOUND_FILE_BY_KIND,
    config_field_for_kind,
    copy_sound_file,
    is_supported_sound_file,
    portable_sound_dir,
    resolve_sound_path,
    sound_dir,
)


def test_supported_sound_files_are_mp3_and_wav_only() -> None:
    """Only common Qt-playable user audio formats should be accepted."""
    assert is_supported_sound_file(Path("done.mp3"))
    assert is_supported_sound_file(Path("done.MP3"))
    assert is_supported_sound_file(Path("alert.wav"))
    assert not is_supported_sound_file(Path("alert.ogg"))
    assert not is_supported_sound_file(Path("alert.txt"))


def test_config_field_for_kind_maps_all_alerts() -> None:
    """Each alert kind should have one persisted custom-path field."""
    assert config_field_for_kind(AlertKind.COMPLETED) == "sound_completed_path"
    assert config_field_for_kind(AlertKind.WAITING_APPROVAL) == "sound_waiting_approval_path"
    assert (
        config_field_for_kind(AlertKind.WAITING_USER_INPUT)
        == "sound_waiting_user_input_path"
    )
    assert config_field_for_kind(AlertKind.ERROR) == "sound_error_path"


def test_sound_dir_defaults_to_portable_project_folder() -> None:
    """Custom sounds should live beside the distributed app, not in AppData."""
    directory = sound_dir()

    assert directory == portable_sound_dir() / "sounds"
    assert "AppData" not in str(directory)


def test_resolve_sound_path_prefers_existing_custom_file(tmp_path: Path) -> None:
    """Configured user sounds should override packaged defaults when present."""
    custom = tmp_path / "custom.wav"
    custom.write_bytes(b"sound")
    config = AppConfig(sound_error_path=str(custom))

    assert resolve_sound_path(AlertKind.ERROR, config) == custom


def test_resolve_sound_path_falls_back_when_custom_file_is_missing(tmp_path: Path) -> None:
    """Missing custom files should not break alert playback."""
    config = AppConfig(sound_completed_path=str(tmp_path / "missing.mp3"))

    path = resolve_sound_path(AlertKind.COMPLETED, config)

    assert path.name == SOUND_FILE_BY_KIND[AlertKind.COMPLETED]


def test_resolve_sound_path_prefers_visible_default_music_folder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The settings experience should use one visible music folder in dev mode."""
    directory = tmp_path / "sounds"
    visible = directory / SOUND_FILE_BY_KIND[AlertKind.COMPLETED]
    visible.parent.mkdir(parents=True)
    visible.write_bytes(b"visible-default")

    monkeypatch.setattr(
        "codex_traffic_lights.sound_settings.sound_dir",
        lambda: directory,
    )

    assert resolve_sound_path(AlertKind.COMPLETED, AppConfig()) == visible


def test_copy_sound_file_copies_supported_file_to_sound_dir(tmp_path: Path) -> None:
    """Choosing a user sound should keep its visible filename after copying."""
    source = tmp_path / "我的提示音.mp3"
    source.write_bytes(b"chosen")
    target_dir = tmp_path / "user-sounds"

    copied = copy_sound_file(source, target_dir, AlertKind.WAITING_APPROVAL)

    assert copied.parent == target_dir
    assert copied.suffix == ".mp3"
    assert copied.read_bytes() == b"chosen"
    assert copied.name == "我的提示音.mp3"


def test_copy_sound_file_rejects_unsupported_files(tmp_path: Path) -> None:
    """Unsupported formats should be rejected before config persistence."""
    source = tmp_path / "alert.ogg"
    source.write_bytes(b"nope")

    with pytest.raises(ValueError, match="MP3/WAV"):
        copy_sound_file(source, tmp_path / "sounds", AlertKind.ERROR)


def test_resolve_sound_path_uses_single_visible_default_folder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default playback should come from sounds/ without packaged-resource fallback."""
    directory = tmp_path / "sounds"
    default = directory / SOUND_FILE_BY_KIND[AlertKind.WAITING_APPROVAL]
    default.parent.mkdir(parents=True)
    default.write_bytes(b"default")

    monkeypatch.setattr(
        "codex_traffic_lights.sound_settings.sound_dir",
        lambda: directory,
    )

    assert resolve_sound_path(AlertKind.WAITING_APPROVAL, AppConfig()) == default
