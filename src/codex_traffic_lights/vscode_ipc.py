"""VSCode Codex private IPC connector.

This module connects to the VSCode Codex extension's private
``\\\\.\\pipe\\codex-ipc`` named pipe. The protocol is not public API and may
change when the OpenAI VSCode extension updates.

The connector deliberately keeps only status-shaped fields. It does not retain
prompt text, generated text, command text, file paths, or raw IPC payloads.
"""

from __future__ import annotations

import ctypes
import json
import re
import struct
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Protocol

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.session_models import SessionRegistry, SessionStatus
from codex_traffic_lights.status_aggregator import aggregate_status, codex_sessions_only

DEFAULT_PIPE_PATH = r"\\.\pipe\codex-ipc"
ENDPOINT_ID = "vscode-ipc"
INITIALIZING_CLIENT_ID = "initializing-client"
CONNECTOR_CLIENT_TYPE = "traffic-lights-connector"
MAX_FRAME_BYTES = 50 * 1024 * 1024
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = -1
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
INFINITE = 0xFFFFFFFF
OPAQUE_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{8,}-[0-9a-fA-F-]{12,}$")


class IpcStream(Protocol):
    """Minimal binary stream surface used by the connector loop."""

    def write_all(self, data: bytes) -> None:
        """Write a complete byte buffer."""

    def read_exact(self, size: int, timeout: float) -> bytes:
        """Read exactly ``size`` bytes or raise ``OSError``."""

    def close(self) -> None:
        """Close the stream."""


class IpcReadTimeoutError(TimeoutError):
    """Raised when no IPC bytes arrive before the read timeout."""


@dataclass
class TurnSummary:
    """Sanitized summary of one Codex turn."""

    status: str | None = None
    thread_id: str | None = None
    started_at_ms: int | None = None
    item_count: int | None = None
    hook_run_count: int | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> TurnSummary:
        """Create a sanitized turn summary from a raw turn payload."""
        params = payload.get("params")
        thread_id: str | None = None
        if isinstance(params, Mapping):
            maybe_thread_id = params.get("threadId")
            thread_id = maybe_thread_id if isinstance(maybe_thread_id, str) else None
        status = payload.get("status")
        return cls(
            status=status if isinstance(status, str) else None,
            thread_id=thread_id,
            started_at_ms=_int_value(payload.get("turnStartedAtMs")),
            item_count=_list_length(payload.get("items")),
            hook_run_count=_list_length(payload.get("hookRuns")),
        )

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-safe dict without sensitive fields."""
        return {
            "status": self.status,
            "threadId": self.thread_id,
            "startedAtMs": self.started_at_ms,
            "itemCount": self.item_count,
            "hookRunCount": self.hook_run_count,
        }


@dataclass
class ConversationSummary:
    """Sanitized per-conversation state tracked in memory."""

    conversation_id: str
    display_name: str | None = None
    revision: int | None = None
    host_id: str | None = None
    runtime_status_type: str | None = None
    active_flags: list[str] = field(default_factory=list)
    turns: list[TurnSummary] = field(default_factory=list)
    approval_signals: list[str] = field(default_factory=list)
    user_input_signals: list[str] = field(default_factory=list)
    plan_confirmation_signals: list[str] = field(default_factory=list)
    signal_patch_paths: list[str] = field(default_factory=list)

    @property
    def last_turn(self) -> TurnSummary | None:
        """Return the latest known turn summary."""
        return self.turns[-1] if self.turns else None


@dataclass(frozen=True)
class StatusTranscript:
    """One redacted status transcript emitted by the connector."""

    conversation_id: str
    revision: int | None
    host_id: str | None
    display_name: str | None
    runtime_status_type: str | None
    active_flags: tuple[str, ...]
    last_turn_status: str | None
    last_turn_started_at_ms: int | None
    product_status: CodexStatus
    turn_count: int
    approval_signals: tuple[str, ...] = ()
    user_input_signals: tuple[str, ...] = ()
    plan_confirmation_signals: tuple[str, ...] = ()
    signal_patch_paths: tuple[str, ...] = ()
    source: str = ENDPOINT_ID

    def to_json_dict(self) -> dict[str, object]:
        """Return the transcript as a JSON-safe object."""
        return {
            "source": self.source,
            "conversationId": self.conversation_id,
            "displayName": self.display_name,
            "hostId": self.host_id,
            "revision": self.revision,
            "runtimeStatus": {
                "type": self.runtime_status_type,
                "activeFlags": list(self.active_flags),
            },
            "lastTurn": {
                "status": self.last_turn_status,
                "startedAtMs": self.last_turn_started_at_ms,
            },
            "productStatus": self.product_status.name,
            "turnCount": self.turn_count,
            "approvalSignals": list(self.approval_signals),
            "userInputSignals": list(self.user_input_signals),
            "planConfirmationSignals": list(self.plan_confirmation_signals),
            "signalPatchPaths": list(self.signal_patch_paths),
        }


class FrameDecoder:
    """Incremental decoder for length-prefixed JSON IPC frames."""

    def __init__(self) -> None:
        """Create an empty frame decoder."""
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[dict[str, object]]:
        """Decode any complete frames from a byte chunk."""
        self._buffer.extend(chunk)
        messages: list[dict[str, object]] = []
        while len(self._buffer) >= 4:
            frame_size = struct.unpack("<I", self._buffer[:4])[0]
            if frame_size > MAX_FRAME_BYTES:
                raise ValueError(f"IPC frame too large: {frame_size}")
            if len(self._buffer) < 4 + frame_size:
                break
            payload = bytes(self._buffer[4 : 4 + frame_size])
            del self._buffer[: 4 + frame_size]
            value = json.loads(payload.decode("utf-8", errors="replace"))
            if isinstance(value, dict):
                messages.append(value)
        return messages


class ConversationStore:
    """In-memory sanitized state for all observed VSCode Codex conversations."""

    def __init__(self) -> None:
        """Create an empty conversation store."""
        self._conversations: dict[str, ConversationSummary] = {}

    def apply_change(
        self,
        conversation_id: str,
        host_id: str | None,
        change: Mapping[str, object],
    ) -> ConversationSummary:
        """Apply a ``thread-stream-state-changed`` change."""
        change_type = change.get("type")
        if change_type == "snapshot":
            return self._apply_snapshot(conversation_id, host_id, change)
        if change_type == "patches":
            return self._apply_patches(conversation_id, host_id, change)
        return self._get_or_create(conversation_id, host_id)

    def _apply_snapshot(
        self,
        conversation_id: str,
        host_id: str | None,
        change: Mapping[str, object],
    ) -> ConversationSummary:
        state_payload = change.get("conversationState")
        state_mapping = state_payload if isinstance(state_payload, Mapping) else None
        summary = ConversationSummary(
            conversation_id=conversation_id,
            display_name=_safe_display_name(conversation_id, state_mapping),
            revision=_int_value(change.get("revision")),
            host_id=host_id,
        )
        if state_mapping is not None:
            state_host = state_mapping.get("hostId")
            if isinstance(state_host, str):
                summary.host_id = state_host
            self._apply_runtime_status(
                summary,
                state_mapping.get("threadRuntimeStatus"),
            )
            self._apply_active_flags(summary, state_mapping.get("activeFlags"))
            self._apply_plan_confirmation(
                summary,
                state_mapping.get("threadGoalResumeConfirmation"),
            )
            turns = state_mapping.get("turns")
            if isinstance(turns, list):
                for turn_index, turn in enumerate(turns):
                    if not isinstance(turn, Mapping):
                        continue
                    summary.turns.append(TurnSummary.from_payload(turn))
                    self._record_snapshot_item_signals(summary, turn_index, turn)
        self._conversations[conversation_id] = summary
        return summary

    def _apply_patches(
        self,
        conversation_id: str,
        host_id: str | None,
        change: Mapping[str, object],
    ) -> ConversationSummary:
        summary = self._get_or_create(conversation_id, host_id)
        revision = _int_value(change.get("revision"))
        if revision is not None:
            summary.revision = revision

        patches = change.get("patches")
        if not isinstance(patches, list):
            return summary

        for patch in patches:
            if not isinstance(patch, Mapping):
                continue
            path = patch.get("path")
            if not isinstance(path, list):
                continue
            value = patch.get("value")
            self._apply_patch_value(summary, path, value)
            self._record_signals(summary, path, value)
        return summary

    def _apply_patch_value(
        self,
        summary: ConversationSummary,
        path: list[object],
        value: object,
    ) -> None:
        if not path:
            return
        if path[0] == "threadRuntimeStatus":
            self._apply_thread_runtime_patch(summary, path, value)
            return
        if path[0] == "activeFlags":
            if len(path) == 1:
                self._apply_active_flags(summary, value)
            elif isinstance(value, str):
                _append_unique(summary.active_flags, value)
            return
        if path[0] == "threadGoalResumeConfirmation":
            self._apply_plan_confirmation_patch(summary, path, value)
            return
        if path[0] != "turns":
            return
        if len(path) >= 2 and isinstance(path[1], int):
            turn_index = path[1]
        else:
            return

        if len(path) == 2 and isinstance(value, Mapping):
            self._set_turn(summary, turn_index, TurnSummary.from_payload(value))
            return

        if len(path) >= 3:
            key = path[2]
            if key == "status" and isinstance(value, str):
                self._ensure_turn(summary, turn_index).status = value
            elif key == "turnStartedAtMs" and isinstance(value, int):
                self._ensure_turn(summary, turn_index).started_at_ms = value
            elif key == "items":
                turn = self._ensure_turn(summary, turn_index)
                item_index = path[3] if len(path) >= 4 and isinstance(path[3], int) else None
                turn.item_count = _bump_count(turn.item_count, item_index)
            elif key == "hookRuns":
                turn = self._ensure_turn(summary, turn_index)
                hook_index = path[3] if len(path) >= 4 and isinstance(path[3], int) else None
                turn.hook_run_count = _bump_count(turn.hook_run_count, hook_index)

    def _apply_thread_runtime_patch(
        self,
        summary: ConversationSummary,
        path: list[object],
        value: object,
    ) -> None:
        if len(path) == 1:
            self._apply_runtime_status(summary, value)
            return
        if len(path) < 2:
            return
        key = path[1]
        if key == "type" and isinstance(value, str):
            summary.runtime_status_type = value
        elif key == "activeFlags":
            if len(path) == 2:
                self._apply_active_flags(summary, value)
            elif isinstance(value, str):
                _append_unique(summary.active_flags, value)

    def _apply_runtime_status(
        self,
        summary: ConversationSummary,
        value: object,
    ) -> None:
        if not isinstance(value, Mapping):
            return
        status_type = value.get("type")
        if isinstance(status_type, str):
            summary.runtime_status_type = status_type
        self._apply_active_flags(summary, value.get("activeFlags"))

    def _apply_active_flags(self, summary: ConversationSummary, value: object) -> None:
        if not isinstance(value, list):
            return
        summary.active_flags = [flag for flag in value if isinstance(flag, str)]

    def _apply_plan_confirmation(
        self,
        summary: ConversationSummary,
        value: object,
    ) -> None:
        summary.plan_confirmation_signals = []
        signal = _extract_plan_confirmation_signal(value)
        if signal is not None:
            summary.plan_confirmation_signals = [f"threadGoalResumeConfirmation:{signal}"]

    def _apply_plan_confirmation_patch(
        self,
        summary: ConversationSummary,
        path: list[object],
        value: object,
    ) -> None:
        if len(path) == 1 or value is None or value is False:
            self._apply_plan_confirmation(summary, value)
            return
        if len(path) == 2 and path[1] in {"status", "state", "type", "kind", "phase"}:
            self._apply_plan_confirmation(summary, value)

    def _record_signals(
        self,
        summary: ConversationSummary,
        path: list[object],
        value: object,
    ) -> None:
        signal_type = _extract_signal_type(value)
        if signal_type is None:
            return

        patch_path = _patch_path(path)
        if _is_approval_signal(signal_type):
            _append_unique(summary.approval_signals, f"type:{signal_type}")
            _append_unique(summary.signal_patch_paths, patch_path)
        if _is_user_input_signal(signal_type):
            _append_unique(summary.user_input_signals, f"type:{signal_type}")
            _append_unique(summary.signal_patch_paths, patch_path)

    def _record_snapshot_item_signals(
        self,
        summary: ConversationSummary,
        turn_index: int,
        turn: Mapping[str, object],
    ) -> None:
        items = turn.get("items")
        if not isinstance(items, list):
            return
        for item_index, item in enumerate(items):
            self._record_signals(summary, ["turns", turn_index, "items", item_index], item)

    def _get_or_create(self, conversation_id: str, host_id: str | None) -> ConversationSummary:
        summary = self._conversations.get(conversation_id)
        if summary is None:
            summary = ConversationSummary(
                conversation_id=conversation_id,
                display_name=_safe_display_name(conversation_id, None),
                host_id=host_id,
            )
            self._conversations[conversation_id] = summary
        elif host_id is not None:
            summary.host_id = host_id
        return summary

    def _ensure_turn(self, summary: ConversationSummary, index: int) -> TurnSummary:
        while len(summary.turns) <= index:
            summary.turns.append(TurnSummary())
        return summary.turns[index]

    def _set_turn(self, summary: ConversationSummary, index: int, turn: TurnSummary) -> None:
        while len(summary.turns) <= index:
            summary.turns.append(TurnSummary())
        summary.turns[index] = turn


class NamedPipeStream:
    """Windows named-pipe stream with overlapped reads.

    Python's standard ``open(r"\\\\.\\pipe\\codex-ipc")`` can block forever while
    waiting for the next frame, so the live connector uses Win32 overlapped I/O.
    The pure parser and connector loop remain mockable through ``IpcStream``.
    """

    def __init__(self, pipe_path: str) -> None:
        """Open a named pipe handle."""
        if sys.platform != "win32":
            raise OSError("VSCode Codex IPC named pipe is only supported on Windows")
        self._handle = _kernel32().CreateFileW(
            pipe_path,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            None,
        )
        if self._handle == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        self._closed = False

    def write_all(self, data: bytes) -> None:
        """Write a complete buffer to the pipe."""
        written = wintypes.DWORD(0)
        ok = _kernel32().WriteFile(
            self._handle,
            ctypes.create_string_buffer(data),
            len(data),
            ctypes.byref(written),
            None,
        )
        if not ok or written.value != len(data):
            raise ctypes.WinError(ctypes.get_last_error())

    def read_exact(self, size: int, timeout: float) -> bytes:
        """Read exactly ``size`` bytes from the pipe."""
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self._read_once(size - len(chunks), timeout)
            chunks.extend(chunk)
        return bytes(chunks)

    def close(self) -> None:
        """Close the pipe handle."""
        if self._closed:
            return
        self._closed = True
        _kernel32().CloseHandle(self._handle)

    def _read_once(self, size: int, timeout: float) -> bytes:
        event = _kernel32().CreateEventW(None, True, False, None)
        if not event:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(size)
        overlapped = _Overlapped()
        overlapped.hEvent = event
        bytes_read = wintypes.DWORD(0)
        try:
            ok = _kernel32().ReadFile(
                self._handle,
                buffer,
                size,
                ctypes.byref(bytes_read),
                ctypes.byref(overlapped),
            )
            if ok:
                if bytes_read.value == 0:
                    raise OSError("named pipe closed")
                return bytes(buffer.raw[: bytes_read.value])

            error = ctypes.get_last_error()
            if error != ERROR_IO_PENDING:
                raise ctypes.WinError(error)

            wait_ms = INFINITE if timeout < 0 else max(0, int(timeout * 1000))
            wait_result = _kernel32().WaitForSingleObject(event, wait_ms)
            if wait_result == WAIT_TIMEOUT:
                _kernel32().CancelIoEx(self._handle, ctypes.byref(overlapped))
                raise IpcReadTimeoutError("no IPC bytes arrived before timeout")
            if wait_result != WAIT_OBJECT_0:
                raise ctypes.WinError(ctypes.get_last_error())

            completed = wintypes.DWORD(0)
            if not _kernel32().GetOverlappedResult(
                self._handle,
                ctypes.byref(overlapped),
                ctypes.byref(completed),
                False,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if completed.value == 0:
                raise OSError("named pipe closed")
            return bytes(buffer.raw[: completed.value])
        finally:
            _kernel32().CloseHandle(event)


class VSCodeIpcConnector(QThread):
    """Read VSCode Codex IPC broadcasts and update the shared session registry."""

    status_changed = pyqtSignal(CodexStatus)
    sessions_changed = pyqtSignal(list)
    session_updated = pyqtSignal(SessionStatus)

    def __init__(
        self,
        config: AppConfig,
        registry: SessionRegistry,
        parent: QObject | None = None,
        *,
        stream_factory: Callable[[], IpcStream] | None = None,
    ) -> None:
        """Create a connector using immutable app config and shared sessions."""
        super().__init__(parent)
        self.config = config
        self.registry = registry
        self._stream_factory = stream_factory
        self._store = ConversationStore()
        self._managed_keys: set[str] = set()
        self._previous_status = aggregate_status(codex_sessions_only(self.registry.get_all()))

    def run(self) -> None:
        """Listen to VSCode Codex IPC until interruption is requested."""
        self._run_loop()

    def _run_loop(
        self,
        *,
        duration: float | None = None,
        max_events: int | None = None,
    ) -> int:
        """Run the connector loop with optional test-only limits."""
        if not self.config.vscode_ipc_enabled:
            return 0

        factory = self._stream_factory or (
            lambda: NamedPipeStream(self.config.vscode_ipc_pipe_path)
        )
        deadline = None if duration is None else time.monotonic() + duration
        emitted = 0

        while self._should_continue(deadline, emitted, max_events):
            stream: IpcStream | None = None
            try:
                stream = factory()
                stream.write_all(encode_frame(build_initialize_request()))
                emitted += self._consume_stream(stream, deadline, emitted, max_events)
            except OSError:
                if self._should_continue(deadline, emitted, max_events):
                    time.sleep(max(0.0, self.config.vscode_ipc_reconnect_delay))
            finally:
                if stream is not None:
                    with suppress(OSError):
                        stream.close()
        return emitted

    def _consume_stream(
        self,
        stream: IpcStream,
        deadline: float | None,
        emitted: int,
        max_events: int | None,
    ) -> int:
        """Read frames from one stream until it disconnects or the loop stops."""
        count = 0
        while self._should_continue(deadline, emitted + count, max_events):
            try:
                message = read_frame(stream, self.config.vscode_ipc_read_timeout)
            except IpcReadTimeoutError:
                continue
            transcript = summarize_ipc_message(message, self._store)
            if transcript is None:
                continue
            self._handle_transcript(transcript)
            count += 1
        return count

    def _handle_transcript(self, transcript: StatusTranscript) -> None:
        """Update registry and emit session/global status signals."""
        session = SessionStatus(
            session_key=_session_key(transcript.conversation_id),
            thread_id=transcript.conversation_id,
            endpoint_id=ENDPOINT_ID,
            display_name=transcript.display_name
            or _safe_display_name(transcript.conversation_id, None),
            status=transcript.product_status,
            last_updated=time.time(),
        )
        self._managed_keys.add(session.session_key)
        self.registry.update(session)
        self.session_updated.emit(session)
        sessions = codex_sessions_only(self.registry.get_all())
        self.sessions_changed.emit(sessions)
        self._emit_aggregate_if_changed(sessions)

    def _expire_stale_working_sessions(self, now: float | None = None) -> None:
        """Keep compatibility with older tests; long tasks no longer expire by time."""
        del now

    def _emit_aggregate_if_changed(self, sessions: list[SessionStatus]) -> None:
        aggregate = aggregate_status(sessions)
        if aggregate is self._previous_status:
            return
        self._previous_status = aggregate
        self.status_changed.emit(aggregate)

    def _should_continue(
        self,
        deadline: float | None,
        emitted: int,
        max_events: int | None,
    ) -> bool:
        if self.isInterruptionRequested():
            return False
        if max_events is not None and emitted >= max_events:
            return False
        return deadline is None or time.monotonic() < deadline


def build_initialize_request() -> dict[str, object]:
    """Build the IPC initialize request for this connector."""
    return {
        "type": "request",
        "requestId": str(uuid.uuid4()),
        "sourceClientId": INITIALIZING_CLIENT_ID,
        "version": 0,
        "method": "initialize",
        "params": {"clientType": CONNECTOR_CLIENT_TYPE},
    }


def encode_frame(message: Mapping[str, object]) -> bytes:
    """Encode one message as a length-prefixed JSON IPC frame."""
    payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return struct.pack("<I", len(payload)) + payload


def read_frame(stream: IpcStream, timeout: float) -> dict[str, object]:
    """Read one JSON IPC frame from a stream."""
    length_bytes = stream.read_exact(4, timeout)
    frame_size = struct.unpack("<I", length_bytes)[0]
    if frame_size > MAX_FRAME_BYTES:
        raise OSError(f"IPC frame too large: {frame_size}")
    payload = stream.read_exact(frame_size, timeout)
    value = json.loads(payload.decode("utf-8", errors="replace"))
    if not isinstance(value, dict):
        raise OSError("IPC frame was not a JSON object")
    return value


def summarize_ipc_message(
    message: Mapping[str, object],
    store: ConversationStore,
) -> StatusTranscript | None:
    """Convert an IPC message into a redacted status transcript when possible."""
    if message.get("type") != "broadcast" or message.get("method") != "thread-stream-state-changed":
        return None
    params = message.get("params")
    if not isinstance(params, Mapping):
        return None
    conversation_id = params.get("conversationId")
    if not isinstance(conversation_id, str) or not conversation_id:
        return None
    host_id_value = params.get("hostId")
    host_id = host_id_value if isinstance(host_id_value, str) else None
    change = params.get("change")
    if not isinstance(change, Mapping):
        return None

    summary = store.apply_change(conversation_id, host_id, change)
    if not _has_observable_status(summary):
        return None
    return _transcript_from_summary(summary)


def _transcript_from_summary(summary: ConversationSummary) -> StatusTranscript:
    last_turn = summary.last_turn
    last_turn_status = last_turn.status if last_turn is not None else None
    last_turn_started_at_ms = last_turn.started_at_ms if last_turn is not None else None
    product_status = _product_status(
        last_turn_status,
        summary.approval_signals,
        summary.user_input_signals,
        last_turn_started_at_ms,
        runtime_status_type=summary.runtime_status_type,
        active_flags=summary.active_flags,
        plan_confirmation_signals=summary.plan_confirmation_signals,
    )
    return StatusTranscript(
        conversation_id=summary.conversation_id,
        revision=summary.revision,
        host_id=summary.host_id,
        display_name=summary.display_name,
        runtime_status_type=summary.runtime_status_type,
        active_flags=tuple(summary.active_flags),
        last_turn_status=last_turn_status,
        last_turn_started_at_ms=last_turn_started_at_ms,
        product_status=product_status,
        turn_count=len(summary.turns),
        approval_signals=tuple(summary.approval_signals),
        user_input_signals=tuple(summary.user_input_signals),
        plan_confirmation_signals=tuple(summary.plan_confirmation_signals),
        signal_patch_paths=tuple(summary.signal_patch_paths),
    )


class _Overlapped(ctypes.Structure):
    """Win32 OVERLAPPED structure for named-pipe reads."""

    _fields_ = (
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    )


_KERNEL32: ctypes.WinDLL | None = None


def _kernel32() -> ctypes.WinDLL:
    """Return kernel32 with the signatures used by the connector."""
    global _KERNEL32
    if _KERNEL32 is not None:
        return _KERNEL32
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE

    kernel32.WriteFile.argtypes = (
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    )
    kernel32.WriteFile.restype = wintypes.BOOL

    kernel32.ReadFile.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_Overlapped),
    )
    kernel32.ReadFile.restype = wintypes.BOOL

    kernel32.CreateEventW.argtypes = (
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    )
    kernel32.CreateEventW.restype = wintypes.HANDLE

    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    kernel32.GetOverlappedResult.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_Overlapped),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
    )
    kernel32.GetOverlappedResult.restype = wintypes.BOOL

    kernel32.CancelIoEx.argtypes = (wintypes.HANDLE, ctypes.POINTER(_Overlapped))
    kernel32.CancelIoEx.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    _KERNEL32 = kernel32
    return kernel32


def _has_observable_status(summary: ConversationSummary) -> bool:
    last_turn = summary.last_turn
    return (
        bool(summary.approval_signals)
        or bool(summary.user_input_signals)
        or bool(summary.plan_confirmation_signals)
        or summary.runtime_status_type is not None
        or bool(summary.active_flags)
        or (last_turn is not None and last_turn.status is not None)
    )


def _product_status(
    last_turn_status: str | None,
    approval_signals: list[str],
    user_input_signals: list[str],
    last_turn_started_at_ms: int | None = None,
    now_ms: int | None = None,
    *,
    runtime_status_type: str | None = None,
    active_flags: list[str] | None = None,
    plan_confirmation_signals: list[str] | None = None,
) -> CodexStatus:
    """Map sanitized IPC fields into the six product statuses."""
    del last_turn_started_at_ms, now_ms
    all_approval_signals = [*approval_signals]
    all_user_input_signals = [*user_input_signals]
    for flag in active_flags or []:
        if _is_approval_signal(flag):
            all_approval_signals.append(f"activeFlag:{flag}")
        if _is_user_input_signal(flag):
            all_user_input_signals.append(f"activeFlag:{flag}")

    if all_approval_signals:
        return CodexStatus.WAITING_APPROVAL
    if plan_confirmation_signals:
        return CodexStatus.WAITING_APPROVAL
    if all_user_input_signals:
        return CodexStatus.WAITING_USER_INPUT
    if runtime_status_type == "active":
        return CodexStatus.WORKING
    if runtime_status_type == "idle":
        return CodexStatus.IDLE
    if runtime_status_type == "systemError":
        return CodexStatus.ERROR
    if last_turn_status == "inProgress":
        return CodexStatus.WORKING
    if last_turn_status == "completed":
        return CodexStatus.IDLE
    if last_turn_status == "failed":
        return CodexStatus.ERROR
    if last_turn_status is None:
        return CodexStatus.OFFLINE
    return CodexStatus.IDLE


def _extract_signal_type(value: object) -> str | None:
    if isinstance(value, Mapping):
        maybe_type = value.get("type")
        if isinstance(maybe_type, str):
            return maybe_type
    return None


def _is_approval_signal(signal_type: str) -> bool:
    lowered = signal_type.casefold()
    return "approval_request" in lowered or (
        "approval" in lowered and "completed" not in lowered and "review" not in lowered
    )


def _is_user_input_signal(signal_type: str) -> bool:
    lowered = signal_type.casefold()
    compact = lowered.replace("_", "").replace("-", "")
    return (
        "request_user_input" in lowered
        or "user_input_request" in lowered
        or "waitingonuserinput" in compact
    )


def _extract_plan_confirmation_signal(value: object) -> str | None:
    if value is None or value is False:
        return None
    if value is True:
        return "present"
    if isinstance(value, str):
        return _plan_confirmation_state(value)
    if isinstance(value, Mapping):
        for key in ("status", "state", "type", "kind", "phase"):
            if key not in value:
                continue
            state = value.get(key)
            if isinstance(state, str):
                return _plan_confirmation_state(state)
            if state is True:
                return "present"
            if state is None or state is False:
                continue
            return None
    return None


def _plan_confirmation_state(value: str) -> str | None:
    lowered = value.casefold()
    compact = lowered.replace("-", "_").replace(" ", "_")
    resolved_terms = ("accepted", "approved", "confirmed", "completed", "done", "resolved")
    if any(term in compact for term in resolved_terms):
        return None
    waiting_terms = ("pending", "waiting", "confirm", "approval", "apply_plan", "resume")
    if any(term in compact for term in waiting_terms):
        return compact[:48]
    return None


def _session_key(conversation_id: str) -> str:
    return f"{ENDPOINT_ID}::{conversation_id}"


def _safe_display_name(conversation_id: str, state_payload: Mapping[str, object] | None) -> str:
    """Return a readable name without using prompt text, generated text, or paths."""
    if state_payload is not None:
        for key in ("displayName", "display_name", "title", "name", "workspace", "repo"):
            value = state_payload.get(key)
            if isinstance(value, str) and value.strip():
                return _truncate_display_name(value.strip())
    if OPAQUE_ID_PATTERN.fullmatch(conversation_id):
        return f"会话 {conversation_id[-3:]}"
    return _truncate_display_name(conversation_id)


def _truncate_display_name(value: str) -> str:
    return value[:12] if len(value) > 12 else value


def _patch_path(path: list[object]) -> str:
    return "/" + "/".join(str(part) for part in path)


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _list_length(value: object) -> int | None:
    return len(value) if isinstance(value, list) else None


def _bump_count(current: int | None, index: int | None) -> int:
    if index is None:
        return 1 if current is None else current
    return max(current or 0, index + 1)


def _int_value(value: object) -> int | None:
    return value if isinstance(value, int) else None
