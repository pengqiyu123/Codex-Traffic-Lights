"""Process monitor with conservative psutil fallback detection."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping

import psutil
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.session_models import SessionRegistry, SessionStatus
from codex_traffic_lights.state_mapper import CodexStateMapper
from codex_traffic_lights.status_aggregator import aggregate_status

ONLINE_STATUSES: frozenset[CodexStatus] = frozenset(
    {
        CodexStatus.IDLE,
        CodexStatus.WORKING,
        CodexStatus.WAITING_APPROVAL,
        CodexStatus.WAITING_USER_INPUT,
    }
)
SELF_PROCESS_TOKENS: tuple[str, ...] = ("codex-traffic-lights", "codex_traffic_lights")


class ProcessMonitor(QThread):
    """Monitor Codex process state and emit product status changes."""

    status_changed = pyqtSignal(CodexStatus)
    sessions_changed = pyqtSignal(list)

    def __init__(self, config: AppConfig, parent: QObject | None = None) -> None:
        """Create a process monitor using immutable application configuration."""
        super().__init__(parent)
        self.config = config
        self.registry = SessionRegistry()
        self._previous_status: CodexStatus = CodexStatus.OFFLINE

    def run(self) -> None:
        """Poll fallback process state until the thread is interrupted."""
        poll_interval_ms = max(1, self.config.poll_interval_ms)
        while not self.isInterruptionRequested():
            self._set_status(self._detect_fallback_status())
            self.msleep(poll_interval_ms)

    def _detect_fallback_status(self) -> CodexStatus:
        """Detect Codex status using only process presence as a fallback signal."""
        if self._has_matching_codex_process():
            return CodexStatus.IDLE
        if self._previous_status in ONLINE_STATUSES:
            return CodexStatus.ERROR
        return CodexStatus.OFFLINE

    def apply_app_server_event(self, event: Mapping[str, object]) -> None:
        """Apply a Codex app-server event and emit the aggregated product status."""
        mapped_status = CodexStateMapper.map_event(event)
        if mapped_status is None:
            return

        thread_id = _extract_string(event, "threadId", "thread_id")
        if thread_id is None:
            self._set_status(mapped_status)
            return

        endpoint_id = (
            _extract_string(event, "endpointId", "endpoint_id")
            or self.config.app_server_url
            or "app-server"
        )
        display_name = _display_name_from_event(event, thread_id)
        self.registry.update(
            SessionStatus(
                session_key=f"{endpoint_id}::{thread_id}",
                thread_id=thread_id,
                endpoint_id=endpoint_id,
                display_name=display_name,
                status=mapped_status,
                last_updated=time.time(),
            )
        )
        self.sessions_changed.emit(self.registry.get_all())
        self._set_status(aggregate_status(self.registry.get_all()))

    def _set_status(self, status: CodexStatus) -> None:
        """Update previous status and emit only when the value changes."""
        if status is self._previous_status:
            return
        self._previous_status = status
        self.status_changed.emit(status)

    def _has_matching_codex_process(self) -> bool:
        """Return True when any process name or command line contains the configured name."""
        process_name = self.config.codex_process_name.casefold()
        current_pid = os.getpid()
        for process in psutil.process_iter():
            if getattr(process, "pid", None) == current_pid:
                continue
            try:
                name = process.name()
                command_line = process.cmdline()
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue

            if _is_traffic_lights_process(name, command_line):
                continue
            if _contains_token(name, process_name):
                return True
            if any(_contains_token(argument, process_name) for argument in command_line):
                return True
        return False


def _contains_token(value: object, token: str) -> bool:
    """Return True when a string value contains a case-insensitive token."""
    return isinstance(value, str) and token in value.casefold()


def _is_traffic_lights_process(name: object, command_line: list[str]) -> bool:
    """Return True when process metadata belongs to this monitoring app."""
    values: list[object] = [name, *command_line]
    return any(
        _contains_token(value, self_token)
        for value in values
        for self_token in SELF_PROCESS_TOKENS
    )


def _extract_string(mapping: Mapping[str, object], *keys: str) -> str | None:
    """Extract the first non-empty string value from a mapping."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _display_name_from_event(event: Mapping[str, object], fallback: str) -> str:
    """Return a short display name for thread-scoped app-server events."""
    for key in ("display_name", "name", "workspace", "repo", "repository"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        basename = _path_basename(cwd)
        if basename:
            return basename

    return fallback[:12] if len(fallback) > 12 else fallback


def _path_basename(value: str) -> str:
    """Extract a basename from POSIX or Windows-looking paths."""
    normalized = value.replace("\\", "/").rstrip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]
