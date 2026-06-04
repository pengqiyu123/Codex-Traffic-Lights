"""Tests for installing and removing hook bridge entries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_traffic_lights import hook_installer
from codex_traffic_lights.hook_installer import (
    HookInstaller,
    resolve_python_executable,
    verify_can_import_hook_scripts,
)


def _read_json(path: Path) -> dict[str, object]:
    """Read a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_install_codex_hooks_preserves_existing_hooks_and_is_idempotent(tmp_path: Path) -> None:
    """Codex hook install should append/update only Codex Traffic Lights entries."""
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    hooks_path = codex_dir / "hooks.json"
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "echo existing"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    installer = HookInstaller(home=tmp_path, python_executable="python")

    installer.install_codex_hooks()
    installer.install_codex_hooks()

    data = _read_json(hooks_path)
    pre_tool_use = data["hooks"]["PreToolUse"]  # type: ignore[index]
    our_entries = [
        entry
        for entry in pre_tool_use
        if "codex_traffic_lights.hook_scripts.codex_hook" in entry["hooks"][0]["command"]
    ]
    assert len(our_entries) == 1
    assert any(entry["hooks"][0]["command"] == "echo existing" for entry in pre_tool_use)
    assert "SessionStart" in data["hooks"]  # type: ignore[operator]
    assert list(codex_dir.glob("hooks.json.bak-*"))
    assert installer.is_installed() is True


def test_install_claude_hooks_preserves_existing_settings(tmp_path: Path) -> None:
    """Claude hook install should preserve unrelated settings and hooks."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "model": "existing",
                "hooks": {
                    "Stop": [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": "echo existing"}],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    installer = HookInstaller(home=tmp_path, python_executable="python")

    installer.install_claude_hooks()

    data = _read_json(settings_path)
    stop_entries = data["hooks"]["Stop"]  # type: ignore[index]
    assert data["model"] == "existing"
    assert any(entry["hooks"][0]["command"] == "echo existing" for entry in stop_entries)
    assert any(
        "codex_traffic_lights.hook_scripts.claude_code_hook" in entry["hooks"][0]["command"]
        for entry in stop_entries
    )
    assert list(claude_dir.glob("settings.json.bak-*"))


def test_uninstall_removes_only_our_hook_entries(tmp_path: Path) -> None:
    """Uninstall should leave user hooks in place while removing bridge hooks."""
    installer = HookInstaller(home=tmp_path, python_executable="python")
    installer.install_codex_hooks()
    installer.install_claude_hooks()

    codex_hooks_path = tmp_path / ".codex" / "hooks.json"
    codex_data = _read_json(codex_hooks_path)
    codex_data["hooks"]["PreToolUse"].append(  # type: ignore[index]
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo keep"}]}
    )
    codex_hooks_path.write_text(json.dumps(codex_data), encoding="utf-8")

    installer.uninstall()

    data = _read_json(codex_hooks_path)
    pre_tool_use = data["hooks"]["PreToolUse"]  # type: ignore[index]
    assert any(entry["hooks"][0]["command"] == "echo keep" for entry in pre_tool_use)
    assert not any(
        "codex_traffic_lights.hook_scripts" in entry["hooks"][0]["command"]
        for event_entries in data["hooks"].values()  # type: ignore[union-attr]
        for entry in event_entries
    )
    assert installer.is_installed() is False


def test_resolve_picks_sys_executable_when_it_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver should prefer the current interpreter when it can import hook scripts."""
    checked: list[str] = []

    def fake_verify(candidate: str) -> bool:
        checked.append(candidate)
        return True

    monkeypatch.setattr(hook_installer.sys, "executable", r"C:\Python\python.exe")
    monkeypatch.setattr(hook_installer, "verify_can_import_hook_scripts", fake_verify)

    assert resolve_python_executable() == r"C:\Python\python.exe"
    assert checked == [r"C:\Python\python.exe"]


def test_resolve_falls_back_to_venv_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Resolver should switch to project .venv Python when sys.executable cannot import."""
    project_root = tmp_path
    (project_root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    def fake_verify(candidate: str) -> bool:
        return Path(candidate) == venv_python

    monkeypatch.setattr(hook_installer.sys, "executable", r"C:\Python\python.exe")
    monkeypatch.setattr(hook_installer, "_find_project_root", lambda: project_root)
    monkeypatch.setattr(hook_installer, "verify_can_import_hook_scripts", fake_verify)

    with caplog.at_level("INFO"):
        assert resolve_python_executable() == str(venv_python)

    assert "Switching hook Python executable" in caplog.text


def test_resolve_normalizes_pythonw_to_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GUI startup with pythonw should still register console Python for hooks."""
    project_root = tmp_path
    (project_root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    scripts_dir = project_root / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True)
    python = scripts_dir / "python.exe"
    pythonw = scripts_dir / "pythonw.exe"
    python.write_text("", encoding="utf-8")
    pythonw.write_text("", encoding="utf-8")

    checked: list[str] = []

    def fake_verify(candidate: str) -> bool:
        checked.append(candidate)
        return Path(candidate) == python

    monkeypatch.setattr(hook_installer.sys, "executable", str(pythonw))
    monkeypatch.setattr(hook_installer, "_find_project_root", lambda: project_root)
    monkeypatch.setattr(hook_installer, "verify_can_import_hook_scripts", fake_verify)

    assert resolve_python_executable() == str(python)
    assert checked == [str(python)]


def test_resolve_warns_when_no_candidate_works(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Resolver should warn and fall back to sys.executable if no candidate imports."""
    monkeypatch.setattr(hook_installer.sys, "executable", r"C:\Python\python.exe")
    monkeypatch.setattr(hook_installer, "verify_can_import_hook_scripts", lambda _: False)

    with caplog.at_level("WARNING"):
        assert resolve_python_executable() == r"C:\Python\python.exe"

    assert "No hook Python candidate can import codex_traffic_lights.hook_scripts" in caplog.text


def test_verify_can_import_returns_true_for_working_python() -> None:
    """A resolver-selected real Python should be able to import hook scripts."""
    assert verify_can_import_hook_scripts(resolve_python_executable()) is True


def test_verify_can_import_returns_false_for_bad_path(tmp_path: Path) -> None:
    """A missing Python path should fail verification instead of raising."""
    assert verify_can_import_hook_scripts(str(tmp_path / "missing-python.exe")) is False


def test_explicit_python_executable_skips_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tests and callers passing python_executable should keep the existing direct behavior."""
    monkeypatch.setattr(
        hook_installer,
        "resolve_python_executable",
        lambda: pytest.fail("resolver should not be called"),
    )

    installer = HookInstaller(home=tmp_path, python_executable="python")

    assert installer.python_executable == "python"
