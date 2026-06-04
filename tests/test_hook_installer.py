"""Tests for installing and removing hook bridge entries."""

from __future__ import annotations

import json
from pathlib import Path

from codex_traffic_lights.hook_installer import HookInstaller


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
