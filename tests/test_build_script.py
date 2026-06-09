"""Tests for the PyInstaller build script."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def import_build_module() -> ModuleType:
    """Import the build script module."""
    script_path = Path("scripts/build.py")
    spec = importlib.util.spec_from_file_location("scripts.build", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_command_matches_pyinstaller_contract() -> None:
    """build_command should build the portable onedir distribution."""
    build = import_build_module()

    assert build.build_command() == [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "Codex Traffic Lights Portable",
        "--add-data",
        "src/codex_traffic_lights/resources;codex_traffic_lights/resources",
        "--icon",
        "src/codex_traffic_lights/resources/icons/app.ico",
        "src/codex_traffic_lights/__main__.py",
    ]


def test_build_main_returns_pyinstaller_exit_code(monkeypatch: object) -> None:
    """main should execute PyInstaller and return its exit code."""
    build = import_build_module()
    calls: list[tuple[list[str], bool]] = []
    prepared: list[Path] = []

    class Result:
        returncode = 7

    def fake_run(command: list[str], check: bool) -> Result:
        calls.append((command, check))
        return Result()

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    monkeypatch.setattr(build, "prepare_portable_folder", prepared.append)

    assert build.main() == 7
    assert calls == [(build.build_command(), False)]
    assert prepared == []


def test_build_main_prepares_portable_assets_after_success(
    monkeypatch: object,
) -> None:
    """Successful builds should copy visible sounds and user guide."""
    build = import_build_module()
    prepared: list[Path] = []

    class Result:
        returncode = 0

    def fake_run(command: list[str], check: bool) -> Result:
        return Result()

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    monkeypatch.setattr(build, "prepare_portable_folder", prepared.append)

    assert build.main() == 0
    assert prepared == [Path("dist") / "Codex Traffic Lights Portable"]


def test_prepare_portable_folder_copies_user_facing_files(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    """Portable folders should expose sounds and a Chinese user guide."""
    build = import_build_module()
    source_sounds = tmp_path / "source-sounds"
    source_sounds.mkdir()
    guide = tmp_path / "guide.md"
    guide.write_text("用户说明", encoding="utf-8")
    for filename in build.DEFAULT_SOUND_FILES:
        (source_sounds / filename).write_bytes(filename.encode("utf-8"))
    dist_dir = tmp_path / "dist"

    monkeypatch.setattr(build, "SOUND_DIR", source_sounds)
    monkeypatch.setattr(build, "USER_GUIDE", guide)

    build.prepare_portable_folder(dist_dir)

    assert (dist_dir / "使用说明.md").read_text(encoding="utf-8") == "用户说明"
    assert sorted(path.name for path in (dist_dir / "sounds").iterdir()) == sorted(
        build.DEFAULT_SOUND_FILES
    )


def test_packaging_resource_paths_exist() -> None:
    """The PyInstaller resource, icon, sound, and guide paths should exist."""
    resources = Path("src/codex_traffic_lights/resources")
    icon = resources / "icons" / "app.ico"
    sound_dir = Path("sounds")
    guide = Path("docs") / "Portable-User-Guide.md"

    assert resources.is_dir()
    assert icon.is_file()
    assert sound_dir.is_dir()
    assert guide.is_file()
    for filename in [
        "任务完成.mp3",
        "待审批确认.mp3",
        "计划模式输入.mp3",
        "运行异常.mp3",
    ]:
        assert (sound_dir / filename).is_file()
