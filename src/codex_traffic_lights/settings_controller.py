"""Settings button wiring and configuration persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from codex_traffic_lights.config import ConfigManager
from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.widgets.side_buttons import PaintedIconButton


class SettingsController:
    """Manage notification/sound toggle buttons and persist config."""

    def __init__(
        self,
        config: AppConfig,
        config_manager: ConfigManager,
        notification_button: PaintedIconButton,
        sound_button: PaintedIconButton,
        on_config_changed: Callable[[AppConfig], None],
    ) -> None:
        """Create a controller for user-facing persistent switches."""
        self._config = config
        self._config_manager = config_manager
        self._on_config_changed = on_config_changed
        notification_button.setChecked(config.notification_enabled)
        sound_button.setChecked(not config.sound_enabled)
        notification_button.toggled.connect(self._set_notification_enabled)
        sound_button.toggled.connect(self._set_muted)

    def _set_notification_enabled(self, checked: bool) -> None:
        """Persist the notification switch."""
        self._update_config(replace(self._config, notification_enabled=checked))

    def _set_muted(self, checked: bool) -> None:
        """Persist inverse sound switch polarity from the mute button."""
        self._update_config(replace(self._config, sound_enabled=not checked))

    def _update_config(self, config: AppConfig) -> None:
        """Save a new config and notify runtime controllers."""
        self._config = config
        self._config_manager.save(config)
        self._on_config_changed(config)
