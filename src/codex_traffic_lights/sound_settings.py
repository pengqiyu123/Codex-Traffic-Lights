"""Custom alert sound file management."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.notification_policy import AlertKind

SUPPORTED_SOUND_SUFFIXES = frozenset((".mp3", ".wav"))

SOUND_FILE_BY_KIND = {
    AlertKind.COMPLETED: "任务完成.mp3",
    AlertKind.WAITING_APPROVAL: "待审批确认.mp3",
    AlertKind.WAITING_USER_INPUT: "计划模式输入.mp3",
    AlertKind.ERROR: "运行异常.mp3",
}

_CONFIG_FIELD_BY_KIND = {
    AlertKind.COMPLETED: "sound_completed_path",
    AlertKind.WAITING_APPROVAL: "sound_waiting_approval_path",
    AlertKind.WAITING_USER_INPUT: "sound_waiting_user_input_path",
    AlertKind.ERROR: "sound_error_path",
}


def config_field_for_kind(kind: AlertKind) -> str:
    """Return the AppConfig field that stores a custom sound for an alert."""
    return _CONFIG_FIELD_BY_KIND[kind]


def sound_dir() -> Path:
    """Return the visible portable directory for all alert sound files."""
    return portable_sound_dir() / "sounds"


def portable_sound_dir() -> Path:
    """Return the project or executable folder used by folder-style distribution."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    source_path = Path(__file__).resolve()
    project_root = source_path.parents[2]
    if (project_root / "src" / "codex_traffic_lights").is_dir():
        return project_root
    return Path.cwd()


def is_supported_sound_file(path: Path) -> bool:
    """Return whether the file suffix is supported by the product picker."""
    return path.suffix.casefold() in SUPPORTED_SOUND_SUFFIXES


def copy_sound_file(source: Path, target_dir: Path, kind: AlertKind) -> Path:
    """Copy a selected custom sound into the user sound directory."""
    if not is_supported_sound_file(source):
        raise ValueError("只支持 MP3/WAV 声音文件")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def resolve_sound_path(kind: AlertKind, config: AppConfig | None = None) -> Path:
    """Resolve the best playable sound path for an alert event."""
    if config is not None:
        configured_path = getattr(config, config_field_for_kind(kind))
        if isinstance(configured_path, str) and configured_path:
            path = Path(configured_path)
            if path.is_file():
                return path
    return sound_dir() / SOUND_FILE_BY_KIND[kind]
