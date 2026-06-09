"""PyInstaller build script for Codex Traffic Lights."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RESOURCE_ADD_DATA = "src/codex_traffic_lights/resources;codex_traffic_lights/resources"
ICON = "src/codex_traffic_lights/resources/icons/app.ico"
ENTRYPOINT = "src/codex_traffic_lights/__main__.py"
APP_NAME = "Codex Traffic Lights Portable"
DIST_DIR = Path("dist") / APP_NAME
SOUND_DIR = Path("sounds")
USER_GUIDE = Path("docs") / "Portable-User-Guide.md"
DEFAULT_SOUND_FILES = (
    "任务完成.mp3",
    "待审批确认.mp3",
    "计划模式输入.mp3",
    "运行异常.mp3",
)


def build_command() -> list[str]:
    """Return the PyInstaller command for the Windows portable folder."""
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        APP_NAME,
        "--add-data",
        RESOURCE_ADD_DATA,
        "--icon",
        ICON,
        ENTRYPOINT,
    ]


def main() -> int:
    """Run PyInstaller, prepare the portable folder, and return exit code."""
    _validate_resources()
    completed = subprocess.run(build_command(), check=False)
    if completed.returncode == 0:
        prepare_portable_folder(DIST_DIR)
    return completed.returncode


def prepare_portable_folder(dist_dir: Path) -> None:
    """Copy user-facing portable assets beside the executable."""
    sounds_target = dist_dir / "sounds"
    sounds_target.mkdir(parents=True, exist_ok=True)
    for filename in DEFAULT_SOUND_FILES:
        shutil.copy2(SOUND_DIR / filename, sounds_target / filename)
    shutil.copy2(USER_GUIDE, dist_dir / "使用说明.md")


def _validate_resources() -> None:
    """Fail early if the configured resource paths are missing."""
    missing = [
        path
        for path in [
            Path("src/codex_traffic_lights/resources"),
            SOUND_DIR,
            Path(ICON),
            Path(ENTRYPOINT),
            USER_GUIDE,
            *(SOUND_DIR / filename for filename in DEFAULT_SOUND_FILES),
        ]
        if not path.exists()
    ]
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing PyInstaller resource path(s): {formatted}")


if __name__ == "__main__":
    raise SystemExit(main())
