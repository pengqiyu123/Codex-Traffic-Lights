"""Tests for the Expanded sound settings panel."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.notification_policy import AlertKind
from codex_traffic_lights.widgets.sound_settings_panel import SoundSettingsPanel


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure widget tests have a QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_sound_settings_panel_has_four_operational_rows(tmp_path: Path) -> None:
    """The panel should expose one compact row for each alert sound."""
    panel = SoundSettingsPanel(tmp_path)

    assert panel.row_count == 4
    assert [row.kind for row in panel.rows] == list(AlertKind)
    assert [row.title for row in panel.rows] == [
        "完成:",
        "审批:",
        "计划:",
        "异常:",
    ]
    assert panel.open_folder_button.text() == "打开音乐文件夹"


def test_sound_settings_panel_uses_readable_label_colors(tmp_path: Path) -> None:
    """Sound names should be visible on the dark Expanded panel."""
    panel = SoundSettingsPanel(tmp_path)
    row = panel.rows[0]

    assert "color:" in row.title_label.styleSheet()
    assert "color:" in row.file_label.styleSheet()
    assert row.title_label.width() > 0
    assert row.file_label.minimumWidth() > 0


def test_sound_settings_panel_updates_filename_from_config(tmp_path: Path) -> None:
    """Configured files should be visible as concise filenames."""
    sound = tmp_path / "done.wav"
    sound.write_bytes(b"sound")
    panel = SoundSettingsPanel(tmp_path)

    panel.set_config(AppConfig(sound_completed_path=str(sound)))

    assert panel.filename_for(AlertKind.COMPLETED) == "done.wav"


def test_sound_settings_panel_shows_resolved_default_when_config_is_missing(
    tmp_path: Path,
) -> None:
    """Settings should show the actual four playable sounds, not stale config names."""
    panel = SoundSettingsPanel(tmp_path)

    panel.set_config(AppConfig(sound_completed_path=str(tmp_path / "missing.wav")))

    assert panel.filename_for(AlertKind.COMPLETED) == "任务完成.mp3"
    assert panel.filename_for(AlertKind.WAITING_APPROVAL) == "待审批确认.mp3"
    assert panel.filename_for(AlertKind.WAITING_USER_INPUT) == "计划模式输入.mp3"
    assert panel.filename_for(AlertKind.ERROR) == "运行异常.mp3"


def test_sound_settings_panel_emits_play_choose_and_open_folder(tmp_path: Path) -> None:
    """Panel buttons should emit product actions without handling persistence itself."""
    panel = SoundSettingsPanel(tmp_path)
    played: list[AlertKind] = []
    chosen: list[AlertKind] = []
    opened: list[Path] = []
    panel.play_requested.connect(played.append)
    panel.choose_requested.connect(chosen.append)
    panel.open_folder_requested.connect(opened.append)

    panel.click_play(AlertKind.ERROR)
    panel.click_choose(AlertKind.WAITING_USER_INPUT)
    panel.click_open_folder()

    assert played == [AlertKind.ERROR]
    assert chosen == [AlertKind.WAITING_USER_INPUT]
    assert opened == [tmp_path]


def test_sound_settings_panel_scales_without_changing_row_count(tmp_path: Path) -> None:
    """Expanded zoom should resize settings rows as a real panel, not only the frame."""
    panel = SoundSettingsPanel(tmp_path)
    default_height = panel.rows[0].height()

    panel.set_scale(2.0)

    assert panel.row_count == 4
    assert panel.rows[0].height() > default_height
