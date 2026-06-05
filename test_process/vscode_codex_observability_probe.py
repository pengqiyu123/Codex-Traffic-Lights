"""Read-only probe for VSCode Codex extension observability.

This script collects local evidence about the OpenAI/Codex VSCode extension
without connecting to private IPC sockets or modifying VSCode configuration.
It is a research aid, not a product data source.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

STATUS_TERMS = (
    "thread-stream-state-changed",
    "thread-read-state-changed",
    "client-status-changed",
    "thread/status/changed",
    "turn/started",
    "turn/completed",
    "waitingOnApproval",
    "waitingOnUserInput",
    "systemError",
)


def main() -> int:
    """Run the probe and print a JSON evidence bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument("--log-limit", type=int, default=5, help="Number of recent Codex.log files.")
    args = parser.parse_args()

    report = {
        "probe": "vscode-codex-observability",
        "timestamp": time.time(),
        "rules": {
            "source": "local-readonly-probe",
            "product_data_source": False,
            "ipc_connected": False,
            "config_modified": False,
        },
        "paths": _known_paths(),
        "extensions": _find_extensions(),
        "latest_extension_code": _inspect_latest_extension_code(),
        "vscode_settings": _read_chatgpt_settings(),
        "storage": _inspect_storage(),
        "logs": _inspect_logs(args.log_limit),
        "processes": _inspect_processes(),
        "named_pipes": _inspect_named_pipes(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _known_paths() -> dict[str, str | None]:
    """Return the main paths this probe inspects."""
    return {
        "extensions": _safe_path(Path.home() / ".vscode" / "extensions"),
        "global_storage": _safe_path(_appdata_path("Code", "User", "globalStorage")),
        "workspace_storage": _safe_path(_appdata_path("Code", "User", "workspaceStorage")),
        "logs": _safe_path(_appdata_path("Code", "logs")),
        "settings": _safe_path(_appdata_path("Code", "User", "settings.json")),
    }


def _find_extensions() -> list[dict[str, object]]:
    """Find installed OpenAI ChatGPT/Codex VSCode extensions and package metadata."""
    extension_root = Path.home() / ".vscode" / "extensions"
    rows: list[dict[str, object]] = []
    for directory in sorted(extension_root.glob("openai.chatgpt-*")):
        package_path = directory / "package.json"
        package = _read_json_object(package_path)
        configuration = package.get("contributes", {})
        if isinstance(configuration, dict):
            configuration = configuration.get("configuration", {})
        properties: object = {}
        if isinstance(configuration, dict):
            properties = configuration.get("properties", {})
        cli_setting: object = None
        if isinstance(properties, dict):
            cli_setting = properties.get("chatgpt.cliExecutable")

        rows.append(
            {
                "name": directory.name,
                "path": _safe_path(directory),
                "version": package.get("version"),
                "publisher": package.get("publisher"),
                "package_name": package.get("name"),
                "display_name": package.get("displayName"),
                "main": package.get("main"),
                "chat_sessions": _chat_sessions(package),
                "cli_executable_setting": cli_setting if isinstance(cli_setting, dict) else None,
                "codex_binary_exists": (directory / "bin" / "windows-x86_64" / "codex.exe").is_file(),
            }
        )
    return rows


def _inspect_latest_extension_code() -> dict[str, object]:
    """Inspect string-level evidence in the latest extension bundle."""
    extensions = sorted((Path.home() / ".vscode" / "extensions").glob("openai.chatgpt-*"))
    if not extensions:
        return {"found": False}

    latest = extensions[-1]
    extension_js = latest / "out" / "extension.js"
    if not extension_js.is_file():
        return {"found": False, "extension": latest.name}

    text = extension_js.read_text(encoding="utf-8", errors="replace")
    terms = [
        "startCodexProcess",
        "Spawning codex app-server",
        "app-server",
        "codex-ipc",
        "chatgpt.cliExecutable",
        "registerInternalNotificationHandler",
        "thread/status/changed",
        "turn/completed",
        "thread-stream-state-changed",
        "thread-follower-command-approval-decision",
        "thread-follower-submit-user-input",
    ]
    broadcast_versions = _extract_broadcast_versions(text)
    return {
        "found": True,
        "extension": latest.name,
        "extension_js": _safe_path(extension_js),
        "size_bytes": extension_js.stat().st_size,
        "term_presence": {term: term in text for term in terms},
        "status_term_counts": {term: text.count(term) for term in STATUS_TERMS},
        "broadcast_versions": broadcast_versions,
        "note": "Values in broadcast_versions are IPC message schema versions, not product status counts.",
    }


def _read_chatgpt_settings() -> dict[str, object]:
    """Read only chatgpt.* keys from VSCode user settings."""
    settings_path = _appdata_path("Code", "User", "settings.json")
    settings = _read_json_object(settings_path)
    return {
        key: value
        for key, value in sorted(settings.items())
        if isinstance(key, str) and key.startswith("chatgpt.")
    }


def _inspect_storage() -> dict[str, object]:
    """Inspect VSCode storage keys without dumping stored values."""
    global_storage = _appdata_path("Code", "User", "globalStorage")
    workspace_storage = _appdata_path("Code", "User", "workspaceStorage")
    return {
        "global_storage": _inspect_state_databases(global_storage, limit=3),
        "workspace_storage_recent": _inspect_state_databases(workspace_storage, limit=10),
        "chat_editing_session_files_recent": _recent_chat_editing_sessions(workspace_storage),
    }


def _inspect_state_databases(root: Path, limit: int) -> list[dict[str, object]]:
    """Inspect recent VSCode state databases for Codex/OpenAI related keys."""
    if not root.exists():
        return []
    databases = sorted(root.rglob("state.vscdb"), key=lambda path: path.stat().st_mtime, reverse=True)
    rows: list[dict[str, object]] = []
    for database in databases[:limit]:
        keys: list[str] = []
        error: str | None = None
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=1)
            try:
                for (key,) in connection.execute(
                    """
                    SELECT key
                    FROM ItemTable
                    WHERE key LIKE '%codex%'
                       OR key LIKE '%chatgpt%'
                       OR key LIKE '%openai%'
                    ORDER BY key
                    LIMIT 50
                    """
                ):
                    if isinstance(key, str):
                        keys.append(key)
            finally:
                connection.close()
        except sqlite3.Error as exc:
            error = str(exc)
        rows.append(
            {
                "path": _safe_path(database),
                "mtime": database.stat().st_mtime,
                "keys": keys,
                "error": error,
            }
        )
    return rows


def _recent_chat_editing_sessions(root: Path) -> list[dict[str, object]]:
    """List recent VSCode chat editing session files without content."""
    if not root.exists():
        return []
    files = sorted(
        root.rglob("chatEditingSessions/*/state.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [
        {
            "path": _safe_path(path),
            "size_bytes": path.stat().st_size,
            "mtime": path.stat().st_mtime,
        }
        for path in files[:10]
    ]


def _inspect_logs(limit: int) -> dict[str, object]:
    """Inspect recent VSCode Codex extension logs for status-related markers."""
    logs_root = _appdata_path("Code", "logs")
    if not logs_root.exists():
        return {"codex_logs": []}

    files = sorted(logs_root.rglob("Codex.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    rows: list[dict[str, object]] = []
    for path in files[:limit]:
        counts = {term: 0 for term in STATUS_TERMS}
        samples: list[str] = []
        for line in _iter_text_lines(path):
            matched = False
            for term in STATUS_TERMS:
                if term in line:
                    counts[term] += 1
                    matched = True
            if matched and len(samples) < 8:
                samples.append(_safe_text(line.rstrip("\n"))[:260])
        rows.append(
            {
                "path": _safe_path(path),
                "size_bytes": path.stat().st_size,
                "mtime": path.stat().st_mtime,
                "counts": counts,
                "samples": samples,
            }
        )
    return {"codex_logs": rows}


def _inspect_processes() -> dict[str, object]:
    """Inspect VSCode/Codex processes and TCP connections."""
    process_script = r"""
$rows = Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -eq 'codex.exe' -or
    ($_.Name -eq 'Code.exe' -and $_.CommandLine -match 'openai.chatgpt|app-server|--type=utility|--type=renderer')
  } |
  Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine
$rows | ConvertTo-Json -Depth 4
"""
    processes = _run_powershell_json(process_script)
    process_rows = _ensure_list(processes.get("data"))
    codex_pids = [
        row.get("ProcessId")
        for row in process_rows
        if isinstance(row, dict)
        and str(row.get("Name", "")).lower() == "codex.exe"
        and "app-server" in str(row.get("CommandLine", ""))
    ]
    tcp_rows: list[object] = []
    for pid in codex_pids:
        tcp_script = f"""
$rows = Get-NetTCPConnection -OwningProcess {int(pid)} -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess
$rows | ConvertTo-Json -Depth 4
"""
        result = _run_powershell_json(tcp_script)
        tcp_rows.extend(_ensure_list(result.get("data")))
    return {
        "process_query_error": processes.get("error"),
        "processes": [_sanitize_process(row) for row in process_rows],
        "codex_app_server_pids": codex_pids,
        "codex_app_server_tcp_connections": tcp_rows,
    }


def _inspect_named_pipes() -> dict[str, object]:
    """List matching named pipes without opening them."""
    script = r"""
$pipes = [System.IO.Directory]::GetFiles('\\.\pipe\') |
  Where-Object { $_ -match 'codex|Code|vscode|chatgpt|openai' } |
  Sort-Object
$pipes | ConvertTo-Json -Depth 2
"""
    result = _run_powershell_json(script)
    return {
        "error": result.get("error"),
        "pipes": [_safe_text(str(item)) for item in _ensure_list(result.get("data"))],
    }


def _extract_broadcast_versions(text: str) -> dict[str, int]:
    """Extract IPC broadcast schema versions from the bundled extension code."""
    versions: dict[str, int] = {}
    for name, value in re.findall(r'"([^"]+)":(\d+)', text):
        if name.startswith("thread-") or name == "client-status-changed":
            versions[name] = int(value)
    return {
        key: versions[key]
        for key in sorted(versions)
        if key in {
            "thread-stream-state-changed",
            "thread-read-state-changed",
            "thread-queued-followups-changed",
            "client-status-changed",
        }
    }


def _chat_sessions(package: dict[str, object]) -> list[str]:
    """Extract contributed chat session identifiers from package.json."""
    contributes = package.get("contributes")
    if not isinstance(contributes, dict):
        return []
    sessions = contributes.get("chatSessions")
    if not isinstance(sessions, list):
        return []
    result: list[str] = []
    for item in sessions:
        if isinstance(item, dict):
            identifier = item.get("type") or item.get("id")
            if isinstance(identifier, str):
                result.append(identifier)
    return result


def _run_powershell_json(script: str) -> dict[str, object]:
    """Run a read-only PowerShell script that prints JSON."""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"data": [], "error": str(exc)}
    if completed.returncode != 0:
        return {"data": [], "error": completed.stderr.strip()}
    stdout = completed.stdout.strip()
    if not stdout:
        return {"data": [], "error": None}
    try:
        return {"data": json.loads(stdout), "error": None}
    except json.JSONDecodeError as exc:
        return {"data": stdout, "error": str(exc)}


def _sanitize_process(row: object) -> object:
    """Sanitize paths inside a process row."""
    if not isinstance(row, dict):
        return row
    sanitized = dict(row)
    for key in ("ExecutablePath", "CommandLine"):
        value = sanitized.get(key)
        if isinstance(value, str):
            sanitized[key] = _safe_text(value)
    return sanitized


def _read_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON object, returning an empty object on failure."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _iter_text_lines(path: Path) -> list[str]:
    """Return text lines from a file, tolerating encoding errors."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError:
        return []


def _appdata_path(*parts: str) -> Path:
    """Build a path below APPDATA, falling back to an empty relative path."""
    appdata = os.environ.get("APPDATA")
    if appdata is None:
        return Path(*parts)
    return Path(appdata, *parts)


def _ensure_list(value: object) -> list[object]:
    """Normalize a JSON value to a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _safe_path(path: Path) -> str | None:
    """Return a display path with the user profile redacted."""
    return _safe_text(str(path))


def _safe_text(value: str) -> str:
    """Redact common user-specific path prefixes."""
    home = str(Path.home())
    appdata = os.environ.get("APPDATA")
    result = value.replace(home, "%USERPROFILE%")
    if appdata:
        result = result.replace(appdata, "%APPDATA%")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
