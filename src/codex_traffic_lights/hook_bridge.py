"""Hook event mapping and file polling bridge.

Research notes captured for Task 9A:
- Codex CLI 0.118.0 does not expose a standalone `codex hooks --help` command on this
  machine. The local and reference implementations use `~/.codex/hooks.json` with a
  top-level `hooks` object where each event maps to a list of command hook entries.
- Codex hook commands can pass the event name as a CLI argument while hook payload JSON is
  read from stdin; reference scripts extract `session_id` from stdin JSON.
- Claude Code user hooks live in `~/.claude/settings.json` under the top-level `hooks`
  object. Existing local settings use event keys such as `SessionStart`, `PreToolUse`,
  `PostToolUse`, `PreCompact`, `Stop`, and `SessionEnd`.
- Claude Code hook payloads are read from stdin JSON; reference scripts also use the
  `CLAUDE_CODE_SESSION_ID` environment variable as a session fallback.
- The referenced signal-light projects use file polling plus atomic replacement. This
  Windows implementation uses `os.replace` and avoids POSIX-only file locks.

The module intentionally stays pure Python per Task 9A constraints. `HookFileWatcher`
provides a small QThread-like polling surface and signal object without importing PyQt5.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from codex_traffic_lights._helpers import path_basename
from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.session_models import SessionRegistry, SessionStatus
from codex_traffic_lights.status_aggregator import aggregate_status

CODEX_WORKING_EVENTS: frozenset[str] = frozenset(
    {"UserPromptSubmit", "PreToolUse", "PostToolUse"}
)
CLAUDE_WORKING_EVENTS: frozenset[str] = frozenset(
    {"UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "SubagentStart"}
)
ERROR_STOP_VALUES: frozenset[str] = frozenset(
    {"error", "failed", "failure", "exception", "max_tokens", "max-token"}
)
SESSION_DIR_NAME = ".codex-traffic-lights"


class HookEventMapper:
    """Map Codex and Claude Code hook events into product statuses."""

    @staticmethod
    def map_codex_event(event_name: str, payload: dict[str, object]) -> CodexStatus | None:
        """Map one Codex hook event to a product status, if it should update UI."""
        if event_name == "SessionStart":
            return CodexStatus.IDLE
        if event_name in CODEX_WORKING_EVENTS:
            return CodexStatus.WORKING
        if event_name == "PermissionRequest":
            return CodexStatus.WAITING_APPROVAL
        if event_name == "PostToolUseFailure":
            return CodexStatus.ERROR
        if event_name == "Stop":
            return CodexStatus.ERROR if _is_error_stop(payload) else CodexStatus.IDLE
        return None

    @staticmethod
    def map_claude_event(event_name: str, payload: dict[str, object]) -> CodexStatus | None:
        """Map one Claude Code hook event to a product status, if it should update UI."""
        if event_name == "SessionStart":
            return CodexStatus.IDLE
        if event_name in CLAUDE_WORKING_EVENTS:
            return CodexStatus.WORKING
        if event_name in {"PostToolUseFailure"}:
            return CodexStatus.ERROR
        if event_name == "Stop":
            return CodexStatus.ERROR if _is_error_stop(payload) else CodexStatus.IDLE
        if event_name == "PermissionRequest":
            return CodexStatus.WAITING_APPROVAL
        if event_name == "Notification":
            return CodexStatus.WAITING_USER_INPUT
        if event_name == "SubagentStop":
            return CodexStatus.IDLE
        return None

    @staticmethod
    def _extract_session_key(payload: dict[str, object]) -> str:
        """Extract a stable session key from hook payload fields."""
        for key in ("session_id", "conversation_id", "thread_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            basename = path_basename(cwd.strip())
            if basename:
                return basename
        return "global"

    @staticmethod
    def extract_display_name(payload: dict[str, object], fallback: str) -> str:
        """Extract a short display name for expanded multi-session UI rows."""
        for key in ("display_name", "project_name", "workspace", "repo", "repository"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            basename = path_basename(cwd.strip())
            if basename:
                return basename
        return fallback[:12] if len(fallback) > 12 else fallback


class SimpleSignal:
    """Tiny callback signal used to keep the hook bridge free of PyQt imports."""

    def __init__(self) -> None:
        """Create an empty callback list."""
        self._callbacks: list[Callable[[CodexStatus], None]] = []

    def connect(self, callback: Callable[[CodexStatus], None]) -> None:
        """Register a callback invoked when the signal emits."""
        self._callbacks.append(callback)

    def emit(self, status: CodexStatus) -> None:
        """Invoke all registered callbacks with a status value."""
        for callback in list(self._callbacks):
            callback(status)


class HookFileWatcher:
    """Poll hook session files and emit aggregate status transitions."""

    STALE_AFTER_SECONDS = 300.0
    POLL_INTERVAL_SECONDS = 1.0

    def __init__(
        self,
        config: AppConfig,
        registry: SessionRegistry,
        parent: object | None = None,
    ) -> None:
        """Create a pure-Python watcher for hook session JSON files."""
        del parent
        self.config = config
        self.registry = registry
        self.sessions_dir = default_sessions_dir()
        self.status_changed = SimpleSignal()
        self._previous_status = CodexStatus.OFFLINE
        self._managed_keys: set[str] = set()
        self._managed_files: dict[str, Path] = {}
        self._interruption_requested = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start polling in a daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._interruption_requested = False
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def run(self) -> None:
        """Poll hook files until interruption is requested."""
        while not self.isInterruptionRequested():
            self._scan_sessions_dir()
            time.sleep(self.POLL_INTERVAL_SECONDS)

    def requestInterruption(self) -> None:  # noqa: N802
        """Request the polling loop to stop."""
        self._interruption_requested = True

    def isInterruptionRequested(self) -> bool:  # noqa: N802
        """Return whether the polling loop should stop."""
        return self._interruption_requested

    def wait(self, timeout_ms: int | None = None) -> bool:
        """Wait for the background polling thread to finish."""
        if self._thread is None:
            return True
        timeout = None if timeout_ms is None else timeout_ms / 1000
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _scan_sessions_dir(self) -> None:
        """Read hook session files, update registry, and emit aggregate changes."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        present_keys: set[str] = set()

        for path in self.sessions_dir.glob("*.json"):
            session = self._session_from_file(path)
            if session is None:
                continue
            self.registry.update(session)
            self._managed_keys.add(session.session_key)
            self._managed_files[session.session_key] = path
            present_keys.add(session.session_key)

        for missing_key in set(self._managed_keys) - present_keys:
            self._remove_session(missing_key, remove_file=False)

        self._cleanup_stale()
        self._emit_aggregate_if_changed()

    def _cleanup_stale(self) -> None:
        """Remove sessions that have not updated for five minutes."""
        now = time.time()
        for session in self.registry.get_all():
            if session.session_key not in self._managed_keys:
                continue
            if now - session.last_updated > self.STALE_AFTER_SECONDS:
                self._remove_session(session.session_key, remove_file=True)
        self._emit_aggregate_if_changed()

    def _session_from_file(self, path: Path) -> SessionStatus | None:
        """Parse one session JSON file into a SessionStatus, if valid."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None

        session_key = payload.get("session_key")
        status_name = payload.get("status")
        display_name = payload.get("display_name")
        updated_at = payload.get("updated_at")
        if not (
            isinstance(session_key, str)
            and session_key.strip()
            and isinstance(status_name, str)
            and isinstance(display_name, str)
            and isinstance(updated_at, int | float)
        ):
            return None

        try:
            status = CodexStatus[status_name]
        except KeyError:
            return None

        endpoint_id, thread_id = _split_session_key(session_key)
        return SessionStatus(
            session_key=session_key,
            thread_id=thread_id,
            endpoint_id=endpoint_id,
            display_name=display_name,
            status=status,
            last_updated=float(updated_at),
        )

    def _remove_session(self, session_key: str, *, remove_file: bool) -> None:
        """Remove one managed session and optionally delete its JSON file."""
        self.registry.remove(session_key)
        self._managed_keys.discard(session_key)
        path = self._managed_files.pop(session_key, None)
        if remove_file and path is not None:
            with suppress(FileNotFoundError):
                path.unlink()

    def _emit_aggregate_if_changed(self) -> None:
        """Emit aggregate status only when it changes."""
        aggregate = aggregate_status(self.registry.get_all())
        if aggregate is self._previous_status:
            return
        self._previous_status = aggregate
        self.status_changed.emit(aggregate)


def default_sessions_dir() -> Path:
    """Return the shared hook sessions directory."""
    return Path.home() / SESSION_DIR_NAME / "sessions"


def session_file_path(session_key: str, sessions_dir: Path | None = None) -> Path:
    """Return a Windows-safe JSON file path for a session key."""
    root = default_sessions_dir() if sessions_dir is None else sessions_dir
    digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:24]
    return root / f"{digest}.json"


def write_hook_session(
    *,
    session_key: str,
    status: CodexStatus,
    display_name: str,
    sessions_dir: Path | None = None,
) -> Path:
    """Write one hook session snapshot atomically and return the final path."""
    root = default_sessions_dir() if sessions_dir is None else sessions_dir
    root.mkdir(parents=True, exist_ok=True)
    target = session_file_path(session_key, root)
    payload = {
        "session_key": session_key,
        "status": status.name,
        "display_name": display_name,
        "updated_at": time.time(),
    }
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)
    return target


def remove_hook_session(session_key: str, sessions_dir: Path | None = None) -> None:
    """Remove one hook session file if it exists."""
    path = session_file_path(session_key, sessions_dir)
    with suppress(FileNotFoundError):
        path.unlink()


def _split_session_key(session_key: str) -> tuple[str, str]:
    """Split endpoint/thread compound keys with a hook-safe fallback."""
    if "::" in session_key:
        endpoint_id, thread_id = session_key.split("::", 1)
        return endpoint_id, thread_id
    return "hook", session_key


def _is_error_stop(payload: dict[str, object]) -> bool:
    """Return True when a Stop payload indicates failure."""
    for key in ("status", "stop_reason", "reason"):
        value = payload.get(key)
        if isinstance(value, str) and value.casefold() in ERROR_STOP_VALUES:
            return True
    for key in ("exit_code", "exit_status", "return_code"):
        value = payload.get(key)
        if isinstance(value, int) and value != 0:
            return True
    error_value = payload.get("error")
    return bool(error_value)
