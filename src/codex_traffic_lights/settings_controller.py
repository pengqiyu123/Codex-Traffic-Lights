"""Settings button wiring and configuration persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QWidget

from codex_traffic_lights.config import ConfigManager
from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.notification_policy import AlertKind
from codex_traffic_lights.sound_player import SoundPlayer
from codex_traffic_lights.sound_settings import (
    config_field_for_kind,
    copy_sound_file,
)
from codex_traffic_lights.sound_settings import (
    sound_dir as default_sound_dir,
)
from codex_traffic_lights.widgets.side_buttons import PaintedIconButton
from codex_traffic_lights.widgets.sound_settings_panel import SoundSettingsPanel


class SettingsController:
    """Manage user-facing persistent settings."""

    def __init__(
        self,
        config: AppConfig,
        config_manager: ConfigManager,
        sound_button: PaintedIconButton,
        sound_settings_panel: SoundSettingsPanel,
        sound_player: SoundPlayer,
        on_config_changed: Callable[[AppConfig], None],
        choose_file_fn: Callable[[QWidget, Path], Path | None] | None = None,
        open_folder_fn: Callable[[Path], None] | None = None,
        show_error_fn: Callable[[str], None] | None = None,
        sound_dir: Path | None = None,
    ) -> None:
        """Create a controller for user-facing persistent switches."""
        self._config = config
        self._config_manager = config_manager
        self._on_config_changed = on_config_changed
        self._sound_settings_panel = sound_settings_panel
        self._sound_player = sound_player
        self._choose_file_fn = choose_file_fn or _choose_sound_file
        self._open_folder_fn = open_folder_fn or _open_folder
        self._show_error_fn = show_error_fn or _show_error
        self._sound_dir = sound_dir or default_sound_dir()
        sound_button.setChecked(not config.sound_enabled)
        sound_button.toggled.connect(self._set_muted)
        sound_settings_panel.set_config(config)
        sound_settings_panel.play_requested.connect(self._play_sound)
        sound_settings_panel.choose_requested.connect(self._choose_sound)
        sound_settings_panel.open_folder_requested.connect(self._open_sound_folder)

    def _set_muted(self, checked: bool) -> None:
        """Persist inverse sound switch polarity from the mute button."""
        self._update_config(replace(self._config, sound_enabled=not checked))

    def _play_sound(self, kind: object) -> None:
        """Audition the currently configured sound for an alert event."""
        if isinstance(kind, AlertKind):
            self._sound_player.play(kind)

    def _choose_sound(self, kind: object) -> None:
        """Choose, copy, and persist a custom sound file for one alert event."""
        if not isinstance(kind, AlertKind):
            return
        try:
            source = self._choose_file_fn(self._sound_settings_panel, self._sound_dir)
        except (OSError, RuntimeError) as exc:
            self._show_error_fn(f"无法打开文件选择器：{exc}")
            return
        if source is None:
            return
        try:
            copied = copy_sound_file(source, self._sound_dir, kind)
        except ValueError as exc:
            self._show_error_fn(str(exc))
            return
        field_name = config_field_for_kind(kind)
        self._update_config(replace(self._config, **{field_name: str(copied)}))

    def _open_sound_folder(self, folder: object) -> None:
        """Open the user sound folder from the settings panel."""
        if isinstance(folder, Path):
            folder.mkdir(parents=True, exist_ok=True)
            self._open_folder_fn(folder)

    def _update_config(self, config: AppConfig) -> None:
        """Save a new config and notify runtime controllers."""
        self._config = config
        self._config_manager.save(config)
        self._sound_settings_panel.set_config(config)
        self._on_config_changed(config)


def _choose_sound_file(parent: QWidget, sound_dir: Path) -> Path | None:
    """Open a user audio picker and return the selected path, if any."""
    options = QFileDialog.Options(QFileDialog.DontUseNativeDialog)
    selected, _filter = QFileDialog.getOpenFileName(
        parent,
        "选择提示音",
        str(sound_dir),
        "Audio Files (*.mp3 *.wav)",
        "",
        options,
    )
    return Path(selected) if selected else None


def _open_folder(folder: Path) -> None:
    """Open a local folder with the desktop shell."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def _show_error(message: str) -> None:
    """Show a short user-facing settings error."""
    QMessageBox.warning(None, "声音设置", message)
