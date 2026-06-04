"""Install and uninstall Codex Traffic Lights hook bridge entries."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BRIDGE_MARKER = "codex_traffic_lights.hook_scripts"
CODEX_HOOK_MODULE = "codex_traffic_lights.hook_scripts.codex_hook"
CLAUDE_HOOK_MODULE = "codex_traffic_lights.hook_scripts.claude_code_hook"
CODEX_EVENTS: tuple[str, ...] = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "PostToolUseFailure",
    "Stop",
    "SessionEnd",
)
CLAUDE_EVENTS: tuple[str, ...] = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "SubagentStart",
    "PostToolUseFailure",
    "PermissionRequest",
    "Notification",
    "SubagentStop",
    "Stop",
    "SessionEnd",
)


class HookInstaller:
    """Manage user-level hook config entries for the file bridge."""

    def __init__(
        self,
        home: Path | None = None,
        python_executable: str | None = None,
    ) -> None:
        """Create an installer rooted at a user home directory."""
        self.home = Path.home() if home is None else home
        self.python_executable = sys.executable if python_executable is None else python_executable

    def install_codex_hooks(self) -> None:
        """Install Codex CLI hook commands into ~/.codex/hooks.json."""
        path = self._codex_hooks_path()
        data = _load_json_object(path)
        hooks = _ensure_hooks_object(data)
        for event_name in CODEX_EVENTS:
            command = _build_command(self.python_executable, CODEX_HOOK_MODULE, event_name)
            _upsert_hook_entry(hooks, event_name, command)
        self._write_with_backup(path, data)

    def install_claude_hooks(self) -> None:
        """Install Claude Code hook commands into ~/.claude/settings.json."""
        path = self._claude_settings_path()
        data = _load_json_object(path)
        hooks = _ensure_hooks_object(data)
        for event_name in CLAUDE_EVENTS:
            command = _build_command(self.python_executable, CLAUDE_HOOK_MODULE)
            _upsert_hook_entry(hooks, event_name, command)
        self._write_with_backup(path, data)

    def uninstall(self) -> None:
        """Remove Codex Traffic Lights hook entries while preserving user hooks."""
        for path in (self._codex_hooks_path(), self._claude_settings_path()):
            if not path.exists():
                continue
            data = _load_json_object(path)
            hooks = data.get("hooks")
            if isinstance(hooks, dict):
                _remove_bridge_entries(hooks)
                self._write_with_backup(path, data)

    def is_installed(self) -> bool:
        """Return True when either Codex or Claude hook config contains our commands."""
        for path in (self._codex_hooks_path(), self._claude_settings_path()):
            if not path.exists():
                continue
            data = _load_json_object(path)
            hooks = data.get("hooks")
            if isinstance(hooks, dict) and _contains_bridge_entry(hooks):
                return True
        return False

    def _codex_hooks_path(self) -> Path:
        """Return the Codex hooks config path."""
        return self.home / ".codex" / "hooks.json"

    def _claude_settings_path(self) -> Path:
        """Return the Claude Code settings config path."""
        return self.home / ".claude" / "settings.json"

    def _write_with_backup(self, path: Path, data: dict[str, Any]) -> None:
        """Backup an existing config file and write the new JSON document."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup_path = path.with_name(f"{path.name}.bak-{int(time.time() * 1000)}")
            shutil.copy2(path, backup_path)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from a config path, returning an empty object on failure."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _ensure_hooks_object(data: dict[str, Any]) -> dict[str, Any]:
    """Return the top-level hooks object, creating it when missing or invalid."""
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks
    return hooks


def _build_command(python_executable: str, module: str, event_name: str | None = None) -> str:
    """Build a shell-safe Python module command for hook configs."""
    parts = [python_executable, "-m", module]
    if event_name is not None:
        parts.append(event_name)
    return subprocess.list2cmdline(parts)


def _upsert_hook_entry(hooks: dict[str, Any], event_name: str, command: str) -> None:
    """Append or replace this app's hook entry for one event."""
    entries = hooks.get(event_name)
    if not isinstance(entries, list):
        entries = []
    kept_entries = [entry for entry in entries if not _entry_has_bridge_command(entry)]
    kept_entries.append(
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": 30,
                }
            ],
        }
    )
    hooks[event_name] = kept_entries


def _remove_bridge_entries(hooks: dict[str, Any]) -> None:
    """Remove bridge entries from every event list."""
    for event_name in list(hooks):
        entries = hooks[event_name]
        if not isinstance(entries, list):
            continue
        kept_entries = [entry for entry in entries if not _entry_has_bridge_command(entry)]
        if kept_entries:
            hooks[event_name] = kept_entries
        else:
            del hooks[event_name]


def _contains_bridge_entry(hooks: dict[str, Any]) -> bool:
    """Return True if any hook entry belongs to this app."""
    return any(
        _entry_has_bridge_command(entry)
        for entries in hooks.values()
        if isinstance(entries, list)
        for entry in entries
    )


def _entry_has_bridge_command(entry: object) -> bool:
    """Return True when a hook entry contains our command marker."""
    if not isinstance(entry, dict):
        return False
    hook_defs = entry.get("hooks")
    if not isinstance(hook_defs, list):
        return False
    for hook_def in hook_defs:
        if not isinstance(hook_def, dict):
            continue
        command = hook_def.get("command")
        if isinstance(command, str) and BRIDGE_MARKER in command:
            return True
    return False
