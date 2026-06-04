"""Install and uninstall Codex Traffic Lights hook bridge entries."""

from __future__ import annotations

import json
import logging
import os
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

IMPORT_CHECK_CODE = "import codex_traffic_lights.hook_scripts"
logger = logging.getLogger(__name__)


class HookInstaller:
    """Manage user-level hook config entries for the file bridge."""

    def __init__(
        self,
        home: Path | None = None,
        python_executable: str | None = None,
    ) -> None:
        """Create an installer rooted at a user home directory."""
        self.home = Path.home() if home is None else home
        if python_executable is not None:
            self.python_executable = python_executable
        else:
            self.python_executable = resolve_python_executable()

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


def resolve_python_executable() -> str:
    """Return a Python executable that can import the hook bridge package."""
    candidates = _python_candidates()
    for candidate in candidates:
        if verify_can_import_hook_scripts(candidate):
            if candidate != sys.executable:
                logger.info(
                    "Switching hook Python executable from %s to %s",
                    sys.executable,
                    candidate,
                )
            return candidate

    logger.warning(
        "No hook Python candidate can import codex_traffic_lights.hook_scripts; "
        "falling back to %s",
        sys.executable,
    )
    return sys.executable


def verify_can_import_hook_scripts(python_executable: str) -> bool:
    """Return True if a Python executable can import the hook script package."""
    try:
        completed = subprocess.run(
            [python_executable, "-c", IMPORT_CHECK_CODE],
            check=False,
            capture_output=True,
            env=_import_check_environment(),
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _python_candidates() -> list[str]:
    """Return Python candidates in priority order for hook registration."""
    candidates = [_console_python_for_hooks(Path(sys.executable))]
    project_root = _find_project_root()
    if project_root is not None:
        venv_python = _project_venv_python(project_root)
        if venv_python is not None:
            candidates.append(str(venv_python))
    return _dedupe_strings(candidates)


def _find_project_root() -> Path | None:
    """Find the project root by walking upward from this file to pyproject.toml."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def _project_venv_python(project_root: Path) -> Path | None:
    """Return the project-local virtualenv Python path for this platform."""
    relative_path = (
        Path(".venv") / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else Path(".venv") / "bin" / "python"
    )
    candidate = project_root / relative_path
    return candidate if candidate.is_file() else None


def _console_python_for_hooks(python_executable: Path) -> str:
    """Prefer console Python over pythonw so hook scripts can use stdin/stdout."""
    if python_executable.name.lower() != "pythonw.exe":
        return str(python_executable)
    console_python = python_executable.with_name("python.exe")
    return str(console_python) if console_python.is_file() else str(python_executable)


def _dedupe_strings(values: list[str]) -> list[str]:
    """Return strings once, preserving order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _import_check_environment() -> dict[str, str]:
    """Return an environment that does not rely on a caller-provided PYTHONPATH."""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


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
