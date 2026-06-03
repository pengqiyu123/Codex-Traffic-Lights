"""JSON configuration loading and persistence."""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from codex_traffic_lights.models import AppConfig

DEFAULT_CONFIG_PATH: Path = Path.home() / ".codex-traffic-lights" / "config.json"


class ConfigManager:
    """Load and save AppConfig values as JSON."""

    def __init__(self, config_path: Path | None = None) -> None:
        """Create a manager for a config file path."""
        self.config_path: Path = config_path or DEFAULT_CONFIG_PATH

    def load(self) -> AppConfig:
        """Load configuration from disk, returning defaults on read or parse failure."""
        try:
            raw_config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return AppConfig()

        if not isinstance(raw_config, dict):
            return AppConfig()

        defaults = AppConfig()
        field_names = {field.name for field in fields(AppConfig)}
        merged: dict[str, Any] = {
            field_name: getattr(defaults, field_name) for field_name in field_names
        }
        merged.update(
            {
                key: value
                for key, value in raw_config.items()
                if isinstance(key, str) and key in field_names
            }
        )

        try:
            return AppConfig(**merged)
        except TypeError:
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        """Write configuration to disk, creating parent directories as needed."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            field.name: getattr(config, field.name)
            for field in fields(AppConfig)
        }
        self.config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
