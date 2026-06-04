"""Codex app-server connector for multi-thread session status.

Task 9B research notes:
- Local Codex version: `codex-cli 0.118.0`.
- `codex app-server --help` marks app-server experimental. `--listen` accepts
  `stdio://` by default and `ws://IP:PORT`; no fixed default TCP port is exposed.
- `codex app-server generate-ts --experimental --out <temp>` generated v2 schema files.
  Relevant methods and notifications are:
  `thread/loaded/list`, `thread/read`, `thread/started`, `thread/status/changed`,
  and `thread/closed`.
- `ThreadLoadedListResponse` returns only thread ids, so this connector calls
  `thread/read` for each id to seed `SessionRegistry` with current status and display
  name.
- The generated schema does not expose a dedicated subscribe request for thread status;
  status updates are server notifications.
- Two WebSocket app-server instances were started simultaneously on
  `ws://127.0.0.1:18731` and `ws://127.0.0.1:18732`; both reached listening state.
  Multi-window support therefore needs one configured endpoint per app-server process.
- A quick JSON-line probe against `stdio://` did not produce a confirmed response before
  timeout, so production connection is conservative: WebSocket JSON-RPC is implemented
  for configured `ws://` endpoints, while unsupported/failed transports return False and
  allow HookFileWatcher plus psutil fallback to continue.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
from collections.abc import Iterator, Mapping
from contextlib import suppress
from typing import Protocol, cast
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.session_models import SessionRegistry, SessionStatus
from codex_traffic_lights.state_mapper import CodexStateMapper
from codex_traffic_lights.status_aggregator import aggregate_status

DEFAULT_APP_SERVER_URL = "stdio://"
WEBSOCKET_SCHEME = "ws"
JSON_RPC_TIMEOUT_SECONDS = 3.0


class AppServerTransport(Protocol):
    """Minimal JSON-RPC transport surface used by AppServerConnector."""

    def connect(self) -> bool:
        """Open the transport and return whether it is ready."""

    def call(self, method: str, params: Mapping[str, object]) -> Mapping[str, object] | None:
        """Send a request and return the response result object, if any."""

    def iter_notifications(self) -> Iterator[Mapping[str, object]]:
        """Yield server notification objects until the transport closes."""

    def close(self) -> None:
        """Close the transport."""


class AppServerConnector(QThread):
    """Connect to Codex app-server and update multi-session status registry."""

    RETRY_INTERVAL_MS = 5000

    session_updated = pyqtSignal(SessionStatus)
    status_changed = pyqtSignal(CodexStatus)

    def __init__(
        self,
        config: AppConfig,
        registry: SessionRegistry,
        parent: QObject | None = None,
    ) -> None:
        """Create an app-server connector for one configured endpoint."""
        super().__init__(parent)
        self.config = config
        self.registry = registry
        self.endpoint_url = config.app_server_url or DEFAULT_APP_SERVER_URL
        self.endpoint_id = self.endpoint_url
        self._client: AppServerTransport | None = None
        self._previous_status: CodexStatus = aggregate_status(self.registry.get_all())
        self._display_names: dict[str, str] = {}

    def run(self) -> None:
        """Connect, seed loaded threads, then process server notifications."""
        while not self.isInterruptionRequested():
            if not self._connect():
                self.msleep(self.RETRY_INTERVAL_MS)
                continue

            try:
                with suppress(Exception):
                    self._subscribe_threads()
                    self._consume_notifications()
            finally:
                self._close_client()

            if not self.isInterruptionRequested():
                self.msleep(self.RETRY_INTERVAL_MS)

    def _connect(self) -> bool:
        """Build and open the configured transport, swallowing connection failures."""
        client: AppServerTransport | None = None
        try:
            client = self._build_client()
            if not client.connect():
                client.close()
                return False
        except Exception:
            if client is not None:
                with suppress(Exception):
                    client.close()
            return False

        self._client = client
        return True

    def _build_client(self) -> AppServerTransport:
        """Create a transport for the configured app-server endpoint."""
        if urlparse(self.endpoint_url).scheme == WEBSOCKET_SCHEME:
            return WebSocketJsonRpcClient(self.endpoint_url)
        return UnsupportedAppServerClient(self.endpoint_url)

    def _subscribe_threads(self) -> None:
        """Discover loaded threads and seed registry with their current statuses."""
        client = self._client
        if client is None:
            return

        cursor: str | None = None
        while True:
            response = client.call("thread/loaded/list", {"cursor": cursor, "limit": None})
            if not isinstance(response, Mapping):
                return

            data = response.get("data")
            if not _is_string_list(data):
                return

            for thread_id in data:
                self._read_and_update_thread(client, thread_id)

            next_cursor = response.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                return
            cursor = next_cursor

    def _handle_notification(self, method: str, params: Mapping[str, object]) -> None:
        """Dispatch one app-server server notification."""
        if method == "thread/status/changed":
            self._handle_status_changed(params)
        elif method == "thread/started":
            self._handle_thread_started(params)
        elif method == "thread/closed":
            self._handle_thread_closed(params)

    def _handle_thread_started(self, params: Mapping[str, object]) -> None:
        """Add or update a session from a thread/started notification."""
        thread = params.get("thread")
        if isinstance(thread, Mapping):
            self._update_thread_session(cast(Mapping[str, object], thread), params)

    def _handle_thread_closed(self, params: Mapping[str, object]) -> None:
        """Remove a session from a thread/closed notification."""
        thread_id = _extract_string(params, "threadId", "thread_id")
        if thread_id is None:
            return

        endpoint_id = _extract_string(params, "endpointId", "endpoint_id") or self.endpoint_id
        self.registry.remove(_session_key(endpoint_id, thread_id))
        self._display_names.pop(thread_id, None)
        self._emit_aggregate_if_changed()

    def _handle_status_changed(self, params: Mapping[str, object]) -> None:
        """Update a session from a thread/status/changed notification."""
        thread_id = _extract_string(params, "threadId", "thread_id")
        status_payload = params.get("status")
        if thread_id is None or not isinstance(status_payload, Mapping):
            return

        mapped_status = CodexStateMapper.map_event({"status": status_payload})
        if mapped_status is None:
            return

        endpoint_id = _extract_string(params, "endpointId", "endpoint_id") or self.endpoint_id
        display_name = self._display_names.get(thread_id, thread_id)
        session = SessionStatus(
            session_key=_session_key(endpoint_id, thread_id),
            thread_id=thread_id,
            endpoint_id=endpoint_id,
            display_name=display_name,
            status=mapped_status,
            last_updated=time.time(),
        )
        self._update_session(session)

    def _consume_notifications(self) -> None:
        """Read notifications from the transport until interrupted or closed."""
        client = self._client
        if client is None:
            return

        for notification in client.iter_notifications():
            if self.isInterruptionRequested():
                return
            method = notification.get("method")
            params = notification.get("params")
            if isinstance(method, str) and isinstance(params, Mapping):
                self._handle_notification(method, cast(Mapping[str, object], params))

    def _read_and_update_thread(self, client: AppServerTransport, thread_id: str) -> None:
        """Read one loaded thread and update registry."""
        response = client.call("thread/read", {"threadId": thread_id, "includeTurns": False})
        if not isinstance(response, Mapping):
            return
        thread = response.get("thread")
        if isinstance(thread, Mapping):
            self._update_thread_session(cast(Mapping[str, object], thread), {})

    def _update_thread_session(
        self,
        thread: Mapping[str, object],
        params: Mapping[str, object],
    ) -> None:
        """Convert a Thread payload into SessionStatus and update registry."""
        thread_id = _extract_string(thread, "id", "threadId", "thread_id")
        status_payload = thread.get("status")
        if thread_id is None or not isinstance(status_payload, Mapping):
            return

        mapped_status = CodexStateMapper.map_event({"status": status_payload})
        if mapped_status is None:
            return

        endpoint_id = _extract_string(params, "endpointId", "endpoint_id") or self.endpoint_id
        display_name = _display_name_from_thread(thread, thread_id)
        self._display_names[thread_id] = display_name
        session = SessionStatus(
            session_key=_session_key(endpoint_id, thread_id),
            thread_id=thread_id,
            endpoint_id=endpoint_id,
            display_name=display_name,
            status=mapped_status,
            last_updated=time.time(),
        )
        self._update_session(session)

    def _update_session(self, session: SessionStatus) -> None:
        """Store one session and emit session plus aggregate status changes."""
        self.registry.update(session)
        self.session_updated.emit(session)
        self._emit_aggregate_if_changed()

    def _emit_aggregate_if_changed(self) -> None:
        """Emit aggregate status only when it changes."""
        aggregate = aggregate_status(self.registry.get_all())
        if aggregate is self._previous_status:
            return
        self._previous_status = aggregate
        self.status_changed.emit(aggregate)

    def _close_client(self) -> None:
        """Close and clear the current transport."""
        if self._client is not None:
            with suppress(Exception):
                self._client.close()
            self._client = None


class UnsupportedAppServerClient:
    """Transport placeholder for unsupported endpoints such as unverified stdio."""

    def __init__(self, endpoint_url: str) -> None:
        """Create an unsupported endpoint marker."""
        self.endpoint_url = endpoint_url

    def connect(self) -> bool:
        """Return False so the connector gracefully falls back."""
        return False

    def call(self, method: str, params: Mapping[str, object]) -> Mapping[str, object] | None:
        """Unsupported transports cannot make requests."""
        del method, params
        return None

    def iter_notifications(self) -> Iterator[Mapping[str, object]]:
        """Unsupported transports never yield notifications."""
        return iter(())

    def close(self) -> None:
        """No-op close for unsupported transports."""


class WebSocketJsonRpcClient:
    """Small stdlib WebSocket JSON-RPC client for `ws://` app-server endpoints."""

    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: float = JSON_RPC_TIMEOUT_SECONDS,
    ) -> None:
        """Create a WebSocket transport for one app-server endpoint."""
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self._socket: socket.socket | None = None
        self._next_request_id = 1
        self._queued_notifications: list[Mapping[str, object]] = []

    def connect(self) -> bool:
        """Open the WebSocket and complete the HTTP upgrade handshake."""
        parsed = urlparse(self.endpoint_url)
        if parsed.scheme != WEBSOCKET_SCHEME or parsed.hostname is None:
            return False

        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        sock = socket.create_connection((parsed.hostname, port), timeout=self.timeout_seconds)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{port}\r\n"
            "Connection: Upgrade\r\n"
            "Upgrade: websocket\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = _recv_until(sock, b"\r\n\r\n", self.timeout_seconds)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            sock.close()
            return False

        sock.settimeout(self.timeout_seconds)
        self._socket = sock
        return True

    def call(self, method: str, params: Mapping[str, object]) -> Mapping[str, object] | None:
        """Send one JSON-RPC request and wait for its matching response."""
        request_id = self._next_request_id
        self._next_request_id += 1
        self._send_json({"method": method, "id": request_id, "params": dict(params)})

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            message = self._receive_json()
            if message is None:
                continue
            if message.get("id") == request_id:
                result = message.get("result")
                return cast(Mapping[str, object], result) if isinstance(result, Mapping) else None
            if isinstance(message.get("method"), str):
                self._queued_notifications.append(message)
        return None

    def iter_notifications(self) -> Iterator[Mapping[str, object]]:
        """Yield queued and live server notifications."""
        while True:
            while self._queued_notifications:
                yield self._queued_notifications.pop(0)
            message = self._receive_json()
            if message is None:
                return
            if isinstance(message.get("method"), str):
                yield message

    def close(self) -> None:
        """Close the WebSocket connection."""
        if self._socket is not None:
            with suppress(OSError):
                self._socket.close()
            self._socket = None

    def _send_json(self, payload: Mapping[str, object]) -> None:
        """Serialize and send one JSON text frame."""
        sock = self._require_socket()
        raw_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        sock.sendall(_build_client_text_frame(raw_payload))

    def _receive_json(self) -> dict[str, object] | None:
        """Receive one JSON object text frame."""
        sock = self._require_socket()
        try:
            raw_message = _read_server_text_frame(sock)
        except OSError:
            return None

        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _require_socket(self) -> socket.socket:
        """Return the active socket or raise when disconnected."""
        if self._socket is None:
            raise OSError("app-server websocket is not connected")
        return self._socket


def _display_name_from_thread(thread: Mapping[str, object], fallback: str) -> str:
    """Return the best compact display name for a thread."""
    for key in ("name", "workspace", "repo", "repository"):
        value = thread.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    cwd = thread.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        basename = _path_basename(cwd)
        if basename:
            return basename

    preview = thread.get("preview")
    if isinstance(preview, str) and preview.strip():
        return preview.strip()[:24]

    return fallback[:12] if len(fallback) > 12 else fallback


def _extract_string(mapping: Mapping[str, object], *keys: str) -> str | None:
    """Extract the first non-empty string value from a mapping."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _session_key(endpoint_id: str, thread_id: str) -> str:
    """Build the compound session registry key."""
    return f"{endpoint_id}::{thread_id}"


def _is_string_list(value: object) -> bool:
    """Return True when a value is a list of strings."""
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _path_basename(value: str) -> str:
    """Extract a basename from POSIX or Windows-looking paths."""
    normalized = value.replace("\\", "/").rstrip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]


def _recv_until(sock: socket.socket, marker: bytes, timeout_seconds: float) -> bytes:
    """Receive bytes until marker appears or timeout expires."""
    deadline = time.monotonic() + timeout_seconds
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        joined = b"".join(chunks)
        if marker in joined:
            return joined
    raise OSError("websocket handshake timed out")


def _build_client_text_frame(payload: bytes) -> bytes:
    """Build a masked client-to-server WebSocket text frame."""
    length = len(payload)
    header = bytearray([0x81])
    if length < 126:
        header.append(0x80 | length)
    elif length <= 0xFFFF:
        header.extend([0x80 | 126, *struct.pack("!H", length)])
    else:
        header.extend([0x80 | 127, *struct.pack("!Q", length)])

    mask = os.urandom(4)
    masked_payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header) + mask + masked_payload


def _read_server_text_frame(sock: socket.socket) -> str:
    """Read a single unmasked server WebSocket text frame."""
    header = _recv_exact(sock, 2)
    first, second = header
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F

    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]

    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length)
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

    if opcode == 0x8:
        raise OSError("websocket closed")
    if opcode != 0x1:
        return ""
    return payload.decode("utf-8")


def _recv_exact(sock: socket.socket, byte_count: int) -> bytes:
    """Receive exactly byte_count bytes or raise on disconnect."""
    chunks: list[bytes] = []
    remaining = byte_count
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise OSError("websocket disconnected")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
