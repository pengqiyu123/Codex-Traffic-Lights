"""Tests for the PyInstaller build script."""

from __future__ import annotations

import importlib
import importlib.util
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
    """build_command should return the required PyInstaller command."""
    build = import_build_module()

    assert build.build_command() == [
        "pyinstaller",
        "--onefile",
        "--windowed",
        "--name",
        "codex-traffic-lights",
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

    class Result:
        returncode = 7

    def fake_run(command: list[str], check: bool) -> Result:
        calls.append((command, check))
        return Result()

    monkeypatch.setattr(build.subprocess, "run", fake_run)

    assert build.main() == 7
    assert calls == [(build.build_command(), False)]


def test_packaging_resource_paths_exist() -> None:
    """The PyInstaller resource folder and icon path should exist."""
    resources = Path("src/codex_traffic_lights/resources")
    icon = resources / "icons" / "app.ico"

    assert resources.is_dir()
    assert icon.is_file()
