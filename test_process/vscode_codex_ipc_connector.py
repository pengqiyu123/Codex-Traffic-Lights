"""Prototype VSCode Codex IPC connector.

This module intentionally lives under ``test_process``. It is a technical
validation tool for the private VSCode Codex IPC route, not product code.

The connector only stores status-shaped fields. It does not retain prompt text,
generated text, command text, file paths, or raw IPC payloads.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import struct
import sys
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Protocol, Self

DEFAULT_PIPE_PATH = r"\\.\pipe\codex-ipc"
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
PRODUCT_STATUS_OFFLINE = "OFFLINE"
PRODUCT_STATUS_IDLE = "IDLE"
PRODUCT_STATUS_WORKING = "WORKING"
PRODUCT_STATUS_WAITING_APPROVAL = "WAITING_APPROVAL"
PRODUCT_STATUS_WAITING_USER_INPUT = "WAITING_USER_INPUT"
PRODUCT_STATUS_ERROR = "ERROR"


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


@dataclass(frozen=True)
class IpcConnectorConfig:
    """Runtime options for the IPC connector prototype."""

    pipe_path: str = DEFAULT_PIPE_PATH
    duration: float = 30.0
    max_events: int = 100
    reconnect_delay: float = 1.0
    read_timeout: float = 1.0


@dataclass
class TurnSummary:
    """Sanitized summary of one Codex turn."""

    status: str | None = None
    thread_id: str | None = None
    item_count: int | None = None
    hook_run_count: int | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Self:
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
            item_count=_list_length(payload.get("items")),
            hook_run_count=_list_length(payload.get("hookRuns")),
        )

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-safe dict without sensitive fields."""
        return {
            "status": self.status,
            "threadId": self.thread_id,
            "itemCount": self.item_count,
            "hookRunCount": self.hook_run_count,
        }


@dataclass
class ConversationSummary:
    """Sanitized per-conversation state tracked in memory."""

    conversation_id: str
    revision: int | None = None
    host_id: str | None = None
    turns: list[TurnSummary] = field(default_factory=list)
    approval_signals: list[str] = field(default_factory=list)
    user_input_signals: list[str] = field(default_factory=list)
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
    last_turn_status: str | None
    product_status: str
    turn_count: int
    approval_signals: tuple[str, ...] = ()
    user_input_signals: tuple[str, ...] = ()
    signal_patch_paths: tuple[str, ...] = ()
    source: str = "vscode-ipc"

    def to_json_dict(self) -> dict[str, object]:
        """Return the transcript as a JSON-safe object."""
        return {
            "source": self.source,
            "conversationId": self.conversation_id,
            "hostId": self.host_id,
            "revision": self.revision,
            "lastTurn": {
                "status": self.last_turn_status,
            },
            "productStatus": self.product_status,
            "turnCount": self.turn_count,
            "approvalSignals": list(self.approval_signals),
            "userInputSignals": list(self.user_input_signals),
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
        summary = ConversationSummary(
            conversation_id=conversation_id,
            revision=_int_value(change.get("revision")),
            host_id=host_id,
        )
        if isinstance(state_payload, Mapping):
            state_host = state_payload.get("hostId")
            if isinstance(state_host, str):
                summary.host_id = state_host
            turns = state_payload.get("turns")
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
        if not path or path[0] != "turns":
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
            elif key == "items":
                turn = self._ensure_turn(summary, turn_index)
                item_index = path[3] if len(path) >= 4 and isinstance(path[3], int) else None
                turn.item_count = _bump_count(turn.item_count, item_index)
            elif key == "hookRuns":
                turn = self._ensure_turn(summary, turn_index)
                hook_index = path[3] if len(path) >= 4 and isinstance(path[3], int) else None
                turn.hook_run_count = _bump_count(turn.hook_run_count, hook_index)

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
            summary = ConversationSummary(conversation_id=conversation_id, host_id=host_id)
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


def build_initialize_request() -> dict[str, object]:
    """Build the IPC initialize request for this temporary connector."""
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


def run_connector(
    config: IpcConnectorConfig,
    *,
    stream_factory: Callable[[], IpcStream] | None = None,
    write_line: Callable[[str], None] = print,
) -> int:
    """Run the connector loop until duration or max-events is reached."""
    factory = stream_factory or (lambda: NamedPipeStream(config.pipe_path))
    store = ConversationStore()
    deadline = time.monotonic() + config.duration
    emitted = 0

    while emitted < config.max_events and time.monotonic() < deadline:
        stream: IpcStream | None = None
        try:
            stream = factory()
            stream.write_all(encode_frame(build_initialize_request()))
            while emitted < config.max_events and time.monotonic() < deadline:
                try:
                    message = read_frame(stream, config.read_timeout)
                except IpcReadTimeoutError:
                    continue
                transcript = summarize_ipc_message(message, store)
                if transcript is None:
                    continue
                write_line(json.dumps(transcript.to_json_dict(), ensure_ascii=False))
                emitted += 1
        except OSError:
            if time.monotonic() < deadline and emitted < config.max_events:
                time.sleep(config.reconnect_delay)
        finally:
            if stream is not None:
                with suppress(OSError):
                    stream.close()
    return 0


def main() -> int:
    """Run the VSCode Codex IPC connector prototype."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipe", default=DEFAULT_PIPE_PATH, help="Named pipe path.")
    parser.add_argument("--duration", type=float, default=30.0, help="Maximum seconds to listen.")
    parser.add_argument("--max-events", type=int, default=100, help="Maximum transcripts to print.")
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=1.0,
        help="Seconds between reconnect attempts.",
    )
    args = parser.parse_args()
    return run_connector(
        IpcConnectorConfig(
            pipe_path=args.pipe,
            duration=args.duration,
            max_events=args.max_events,
            reconnect_delay=args.reconnect_delay,
        )
    )


def _transcript_from_summary(summary: ConversationSummary) -> StatusTranscript:
    last_turn = summary.last_turn
    last_turn_status = last_turn.status if last_turn is not None else None
    product_status = _product_status(
        last_turn_status,
        summary.approval_signals,
        summary.user_input_signals,
    )
    return StatusTranscript(
        conversation_id=summary.conversation_id,
        revision=summary.revision,
        host_id=summary.host_id,
        last_turn_status=last_turn_status,
        product_status=product_status,
        turn_count=len(summary.turns),
        approval_signals=tuple(summary.approval_signals),
        user_input_signals=tuple(summary.user_input_signals),
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
        or (last_turn is not None and last_turn.status is not None)
    )


def _product_status(
    last_turn_status: str | None,
    approval_signals: list[str],
    user_input_signals: list[str],
) -> str:
    if approval_signals:
        return PRODUCT_STATUS_WAITING_APPROVAL
    if user_input_signals:
        return PRODUCT_STATUS_WAITING_USER_INPUT
    if last_turn_status == "inProgress":
        return PRODUCT_STATUS_WORKING
    if last_turn_status == "completed":
        return PRODUCT_STATUS_IDLE
    if last_turn_status == "failed":
        return PRODUCT_STATUS_ERROR
    if last_turn_status is None:
        return PRODUCT_STATUS_OFFLINE
    return PRODUCT_STATUS_IDLE


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
    return "request_user_input" in lowered or "user_input_request" in lowered


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


if __name__ == "__main__":
    raise SystemExit(main())
