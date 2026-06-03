"""Tests for JSON configuration persistence."""

import json
from pathlib import Path

from codex_traffic_lights.config import ConfigManager
from codex_traffic_lights.models import AppConfig


def test_load_returns_default_config_when_file_is_missing(tmp_path: Path) -> None:
    """A missing config file should not block app startup."""
    manager = ConfigManager(tmp_path / "missing.json")

    assert manager.load() == AppConfig()


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Saved configuration should load back as the same AppConfig."""
    path = tmp_path / "config.json"
    manager = ConfigManager(path)
    config = AppConfig(
        poll_interval_ms=1500,
        codex_process_name="codex-cli",
        app_server_url="ws://127.0.0.1:14567",
        window_scale=1.4,
        notification_enabled=False,
        sound_enabled=False,
    )

    manager.save(config)

    assert manager.load() == config


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    """ConfigManager should create the config directory before writing."""
    path = tmp_path / "nested" / "config.json"
    manager = ConfigManager(path)

    manager.save(AppConfig(sound_enabled=False))

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["sound_enabled"] is False


def test_load_returns_default_config_for_invalid_json(tmp_path: Path) -> None:
    """Invalid JSON should fall back to defaults instead of crashing."""
    path = tmp_path / "config.json"
    path.write_text("{not valid json", encoding="utf-8")
    manager = ConfigManager(path)

    assert manager.load() == AppConfig()


def test_load_merges_missing_fields_with_defaults(tmp_path: Path) -> None:
    """Partial config files should be upgraded with AppConfig defaults."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"poll_interval_ms": 5000, "notification_enabled": False}),
        encoding="utf-8",
    )
    manager = ConfigManager(path)

    assert manager.load() == AppConfig(
        poll_interval_ms=5000,
        notification_enabled=False,
    )
