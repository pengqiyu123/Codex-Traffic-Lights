"""Expanded-mode custom alert sound settings panel."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from codex_traffic_lights.models import AppConfig
from codex_traffic_lights.notification_policy import AlertKind
from codex_traffic_lights.sound_settings import SOUND_FILE_BY_KIND, resolve_sound_path

BASE_ROW_HEIGHT = 26
BASE_PANEL_MARGIN = 4
BASE_SPACING = 3
BASE_TITLE_WIDTH = 30
BASE_BUTTON_WIDTH = 36
BASE_FOLDER_HEIGHT = 24
BASE_TITLE_FONT_SIZE = 8
BASE_FILE_FONT_SIZE = 7
MIN_SCALE = 0.5
MAX_SCALE = 2.0

_TITLE_BY_KIND = {
    AlertKind.COMPLETED: "完成:",
    AlertKind.WAITING_APPROVAL: "审批:",
    AlertKind.WAITING_USER_INPUT: "计划:",
    AlertKind.ERROR: "异常:",
}


class SoundSettingRow(QWidget):
    """One compact row for a single alert sound assignment."""

    def __init__(self, kind: AlertKind, parent: QWidget | None = None) -> None:
        """Create a row with filename, audition, and choose controls."""
        super().__init__(parent)
        self.kind = kind
        self.title = _TITLE_BY_KIND[kind]
        self._scale = 1.0

        self.title_label = QLabel(self.title, self)
        self.title_label.setObjectName(f"{kind.value}_sound_title")
        self.title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.title_label.setStyleSheet("color: #F4F4F5;")

        self.file_label = QLabel("", self)
        self.file_label.setObjectName(f"{kind.value}_sound_file")
        self.file_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.file_label.setStyleSheet("color: #D6D9DE;")

        self.play_button = QPushButton("试听", self)
        self.play_button.setObjectName(f"{kind.value}_sound_play")
        self.choose_button = QPushButton("选择", self)
        self.choose_button.setObjectName(f"{kind.value}_sound_choose")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(BASE_SPACING)
        layout.addWidget(self.title_label)
        layout.addWidget(self.file_label, 1)
        layout.addWidget(self.play_button)
        layout.addWidget(self.choose_button)
        self.set_filename(SOUND_FILE_BY_KIND[kind])
        self.set_scale(1.0)

    def set_filename(self, filename: str) -> None:
        """Show the active filename for this sound row."""
        self.file_label.setText(filename)

    def set_scale(self, scale: float) -> None:
        """Scale row geometry and text rhythm."""
        self._scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self.setFixedHeight(round(BASE_ROW_HEIGHT * self._scale))
        title_font = QFont("Microsoft YaHei UI", max(7, round(BASE_TITLE_FONT_SIZE * self._scale)))
        title_font.setBold(True)
        file_font = QFont("Microsoft YaHei UI", max(6, round(BASE_FILE_FONT_SIZE * self._scale)))
        self.title_label.setFont(title_font)
        self.title_label.setFixedWidth(round(BASE_TITLE_WIDTH * self._scale))
        self.file_label.setFont(file_font)
        self.file_label.setMinimumWidth(round(70 * self._scale))
        width = round(BASE_BUTTON_WIDTH * self._scale)
        height = round((BASE_ROW_HEIGHT - 4) * self._scale)
        for button in (self.play_button, self.choose_button):
            button.setFixedSize(width, height)
            button.setFont(QFont("Microsoft YaHei UI", max(6, round(7 * self._scale))))
            button.setCursor(Qt.PointingHandCursor)


class SoundSettingsPanel(QWidget):
    """Panel for choosing user-provided alert sound files."""

    play_requested = pyqtSignal(object)
    choose_requested = pyqtSignal(object)
    open_folder_requested = pyqtSignal(object)

    def __init__(self, sound_dir: Path, parent: QWidget | None = None) -> None:
        """Create the compact expanded sound settings panel."""
        super().__init__(parent)
        self._scale = 1.0
        self._sound_dir = sound_dir
        self.rows = [SoundSettingRow(kind, self) for kind in AlertKind]
        self.open_folder_button = QPushButton("打开音乐文件夹", self)
        self.open_folder_button.setObjectName("open_sound_folder_button")
        self.open_folder_button.setCursor(Qt.PointingHandCursor)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            BASE_PANEL_MARGIN,
            BASE_PANEL_MARGIN,
            BASE_PANEL_MARGIN,
            BASE_PANEL_MARGIN,
        )
        self._layout.setSpacing(BASE_SPACING)
        for row in self.rows:
            self._layout.addWidget(row)
            row.play_button.clicked.connect(
                lambda _checked=False, kind=row.kind: self.play_requested.emit(kind)
            )
            row.choose_button.clicked.connect(
                lambda _checked=False, kind=row.kind: self.choose_requested.emit(kind)
            )
        self._layout.addWidget(self.open_folder_button)
        self.open_folder_button.clicked.connect(self.click_open_folder)
        self.set_config(AppConfig())
        self.set_scale(1.0)

    @property
    def row_count(self) -> int:
        """Return the number of alert rows shown in the panel."""
        return len(self.rows)

    def set_config(self, config: AppConfig) -> None:
        """Refresh visible filenames from the current app config."""
        for row in self.rows:
            filename = resolve_sound_path(row.kind, config).name
            row.set_filename(filename)

    def filename_for(self, kind: AlertKind) -> str:
        """Return the visible filename for one alert kind."""
        return self._row_for_kind(kind).file_label.text()

    def click_play(self, kind: AlertKind) -> None:
        """Test helper that clicks the play button for an alert kind."""
        self._row_for_kind(kind).play_button.click()

    def click_choose(self, kind: AlertKind) -> None:
        """Test helper that clicks the choose button for an alert kind."""
        self._row_for_kind(kind).choose_button.click()

    def click_open_folder(self) -> None:
        """Emit a request to open the user sound folder."""
        self.open_folder_requested.emit(self._sound_dir)

    def set_scale(self, scale: float) -> None:
        """Scale all settings rows and panel chrome."""
        self._scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        margin = round(BASE_PANEL_MARGIN * self._scale)
        self._layout.setContentsMargins(margin, margin, margin, margin)
        self._layout.setSpacing(round(BASE_SPACING * self._scale))
        for row in self.rows:
            row.set_scale(self._scale)
        self.open_folder_button.setFixedHeight(round(BASE_FOLDER_HEIGHT * self._scale))
        self.open_folder_button.setFont(
            QFont("Microsoft YaHei UI", max(7, round(8 * self._scale)))
        )

    def _row_for_kind(self, kind: AlertKind) -> SoundSettingRow:
        """Return the row for an alert kind."""
        for row in self.rows:
            if row.kind is kind:
                return row
        raise KeyError(kind)
