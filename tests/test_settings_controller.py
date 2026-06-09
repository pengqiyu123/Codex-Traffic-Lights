"""Tests for settings toggle persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog

from codex_traffic_lights import settings_controller
from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.notification_policy import AlertKind
from codex_traffic_lights.settings_controller import SettingsController
from codex_traffic_lights.widgets.sound_settings_panel import SoundSettingsPanel


@pytest.fixture(autouse=True)
def qapplication() -> QApplication:
    """Ensure QWidget-based settings tests can run standalone."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeSignal:
    """Minimal signal recorder for toggle callbacks."""

    def __init__(self) -> None:
        self.connected_slot: object | None = None

    def connect(self, slot: object) -> None:
        self.connected_slot = slot

    def emit(self, checked: bool) -> None:
        assert callable(self.connected_slot)
        self.connected_slot(checked)


class FakeButton:
    """Small checkable-button stand-in."""

    def __init__(self) -> None:
        self.checked = False
        self.toggled = FakeSignal()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        self.checked = checked

    def isChecked(self) -> bool:  # noqa: N802
        return self.checked


class FakeConfigManager:
    """Record saved configs."""

    def __init__(self) -> None:
        self.saved: list[AppConfig] = []

    def save(self, config: AppConfig) -> None:
        self.saved.append(config)


class FakeSoundPlayer:
    """Record sound audition requests."""

    def __init__(self) -> None:
        self.played: list[AlertKind] = []

    def play(self, kind: AlertKind) -> None:
        self.played.append(kind)


def test_settings_controller_initializes_button_polarity() -> None:
    """Mute uses inverse sound polarity while notification config stays hidden."""
    sound_button = FakeButton()

    SettingsController(
        AppConfig(notification_enabled=True, sound_enabled=False),
        FakeConfigManager(),
        sound_button,
        SoundSettingsPanel(Path("sounds")),
        FakeSoundPlayer(),
        lambda _config: None,
    )

    assert sound_button.isChecked() is True


def test_settings_controller_persists_inverse_mute_toggle() -> None:
    """Checked mute means sound_enabled is false."""
    manager = FakeConfigManager()
    sound_button = FakeButton()
    changed: list[AppConfig] = []
    SettingsController(
        AppConfig(notification_enabled=True, sound_enabled=True),
        manager,
        sound_button,
        SoundSettingsPanel(Path("sounds")),
        FakeSoundPlayer(),
        changed.append,
    )

    sound_button.toggled.emit(True)

    assert manager.saved[-1].sound_enabled is False
    assert manager.saved[-1].notification_enabled is True
    assert changed[-1] == manager.saved[-1]


def test_settings_controller_auditions_panel_sound() -> None:
    """Panel audition requests should play the selected alert kind."""
    sound = FakeSoundPlayer()
    panel = SoundSettingsPanel(Path("sounds"))

    controller = SettingsController(
        AppConfig(),
        FakeConfigManager(),
        FakeButton(),
        panel,
        sound,
        lambda _config: None,
    )

    panel.click_play(AlertKind.ERROR)

    assert controller is not None
    assert sound.played == [AlertKind.ERROR]


def test_settings_controller_persists_chosen_custom_sound(tmp_path: Path) -> None:
    """Choosing a sound should copy it and persist the matching config field."""
    manager = FakeConfigManager()
    sound_button = FakeButton()
    panel = SoundSettingsPanel(tmp_path / "panel-sounds")
    source = tmp_path / "external.wav"
    source.write_bytes(b"custom")
    changed: list[AppConfig] = []

    controller = SettingsController(
        AppConfig(notification_enabled=True, sound_enabled=True),
        manager,
        sound_button,
        panel,
        FakeSoundPlayer(),
        changed.append,
        choose_file_fn=lambda _parent, _sound_dir: source,
        sound_dir=tmp_path / "copied-sounds",
    )

    panel.click_choose(AlertKind.WAITING_USER_INPUT)

    assert controller is not None
    saved_path = Path(manager.saved[-1].sound_waiting_user_input_path or "")
    assert saved_path.is_file()
    assert saved_path.read_bytes() == b"custom"
    assert panel.filename_for(AlertKind.WAITING_USER_INPUT) == saved_path.name
    assert changed[-1] == manager.saved[-1]


def test_settings_controller_reports_unsupported_sound_without_persisting(
    tmp_path: Path,
) -> None:
    """Unsupported picker results should show an error and leave config untouched."""
    manager = FakeConfigManager()
    panel = SoundSettingsPanel(tmp_path / "panel-sounds")
    source = tmp_path / "external.ogg"
    source.write_bytes(b"unsupported")
    errors: list[str] = []

    controller = SettingsController(
        AppConfig(),
        manager,
        FakeButton(),
        panel,
        FakeSoundPlayer(),
        lambda _config: None,
        choose_file_fn=lambda _parent, _sound_dir: source,
        sound_dir=tmp_path / "copied-sounds",
        show_error_fn=errors.append,
    )

    panel.click_choose(AlertKind.ERROR)

    assert controller is not None
    assert manager.saved == []
    assert errors == ["只支持 MP3/WAV 声音文件"]
    assert panel.filename_for(AlertKind.ERROR) == "运行异常.mp3"


def test_settings_controller_ignores_cancelled_sound_selection(
    tmp_path: Path,
) -> None:
    """Closing the file picker without selecting a file should be a no-op."""
    manager = FakeConfigManager()
    panel = SoundSettingsPanel(tmp_path / "panel-sounds")
    errors: list[str] = []

    controller = SettingsController(
        AppConfig(),
        manager,
        FakeButton(),
        panel,
        FakeSoundPlayer(),
        lambda _config: None,
        choose_file_fn=lambda _parent, _sound_dir: None,
        sound_dir=tmp_path / "copied-sounds",
        show_error_fn=errors.append,
    )

    panel.click_choose(AlertKind.COMPLETED)

    assert controller is not None
    assert manager.saved == []
    assert errors == []
    assert panel.filename_for(AlertKind.COMPLETED) == "任务完成.mp3"


def test_settings_controller_reports_file_picker_failure_without_crashing(
    tmp_path: Path,
) -> None:
    """File-picker backend failures should become user-facing errors."""
    manager = FakeConfigManager()
    panel = SoundSettingsPanel(tmp_path / "panel-sounds")
    errors: list[str] = []

    def fail_picker(_parent: object, _sound_dir: Path) -> Path | None:
        raise RuntimeError("dialog closed unexpectedly")

    controller = SettingsController(
        AppConfig(),
        manager,
        FakeButton(),
        panel,
        FakeSoundPlayer(),
        lambda _config: None,
        choose_file_fn=fail_picker,
        sound_dir=tmp_path / "copied-sounds",
        show_error_fn=errors.append,
    )

    panel.click_choose(AlertKind.COMPLETED)

    assert controller is not None
    assert manager.saved == []
    assert errors == ["无法打开文件选择器：dialog closed unexpectedly"]


def test_choose_sound_file_uses_parent_music_folder_and_non_native_dialog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The Windows file picker should close safely without orphaning the app."""
    panel = SoundSettingsPanel(tmp_path / "panel-sounds")
    sound_dir = tmp_path / "sounds"
    captured: dict[str, object] = {}

    def fake_get_open_file_name(
        parent: object,
        caption: str,
        directory: str,
        file_filter: str,
        initial_filter: str = "",
        options: QFileDialog.Options | None = None,
    ) -> tuple[str, str]:
        captured["parent"] = parent
        captured["caption"] = caption
        captured["directory"] = directory
        captured["file_filter"] = file_filter
        captured["initial_filter"] = initial_filter
        captured["options"] = QFileDialog.Options() if options is None else options
        return "", ""

    monkeypatch.setattr(
        settings_controller.QFileDialog,
        "getOpenFileName",
        fake_get_open_file_name,
    )

    selected = settings_controller._choose_sound_file(panel, sound_dir)

    assert selected is None
    assert captured["parent"] is panel
    assert captured["caption"] == "选择提示音"
    assert captured["directory"] == str(sound_dir)
    assert captured["file_filter"] == "Audio Files (*.mp3 *.wav)"
    assert captured["options"] & QFileDialog.DontUseNativeDialog


def test_settings_controller_uses_same_music_folder_for_open_and_choose(
    tmp_path: Path,
) -> None:
    """Open folder and choose dialog should point at the same music directory."""
    sound_dir = tmp_path / "sounds"
    opened: list[Path] = []
    chosen_dirs: list[Path] = []

    def choose(_parent: object, folder: Path) -> Path | None:
        chosen_dirs.append(folder)
        return None

    controller = SettingsController(
        AppConfig(),
        FakeConfigManager(),
        FakeButton(),
        SoundSettingsPanel(sound_dir),
        FakeSoundPlayer(),
        lambda _config: None,
        choose_file_fn=choose,
        open_folder_fn=opened.append,
        sound_dir=sound_dir,
    )

    controller._sound_settings_panel.click_choose(AlertKind.COMPLETED)
    controller._sound_settings_panel.click_open_folder()

    assert chosen_dirs == [sound_dir]
    assert opened == [sound_dir]


def test_settings_controller_opens_sound_folder(tmp_path: Path) -> None:
    """The panel should delegate folder opening to a shell adapter."""
    opened: list[Path] = []
    panel = SoundSettingsPanel(tmp_path / "sounds")
    controller = SettingsController(
        AppConfig(),
        FakeConfigManager(),
        FakeButton(),
        panel,
        FakeSoundPlayer(),
        lambda _config: None,
        open_folder_fn=opened.append,
    )

    panel.click_open_folder()

    assert controller is not None
    assert opened == [tmp_path / "sounds"]
    assert opened[0].is_dir()
