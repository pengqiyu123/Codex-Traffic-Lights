"""Tests for the Codex app-server connector."""

from __future__ import annotations

import json
import struct
from collections.abc import Iterator, Mapping

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.app_server_connector import (
    AppServerConnector,
    UnsupportedAppServerClient,
    WebSocketJsonRpcClient,
    _build_client_text_frame,
    _display_name_from_thread,
    _extract_string,
    _is_string_list,
    _path_basename,
    _read_server_text_frame,
    _recv_exact,
    _recv_until,
    _session_key,
)
from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.session_models import SessionRegistry, SessionStatus


class FakeSocket:
    """Tiny socket stand-in backed by an in-memory receive buffer."""

    def __init__(self, chunks: list[bytes] | None = None) -> None:
        """Create a fake socket with optional bytes returned by recv."""
        self._buffer = bytearray(b"".join(chunks or []))
        self.sent: list[bytes] = []
        self.closed = False
        self.timeout: float | None = None

    def recv(self, size: int) -> bytes:
        """Return up to size bytes from the fake receive buffer."""
        if not self._buffer:
            return b""
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk

    def sendall(self, data: bytes) -> None:
        """Record bytes sent by the client."""
        self.sent.append(data)

    def close(self) -> None:
        """Mark the fake socket as closed."""
        self.closed = True

    def settimeout(self, timeout: float) -> None:
        """Record the configured socket timeout."""
        self.timeout = timeout


class FakeAppServerClient:
    """Small app-server transport fake for connector tests."""

    def __init__(
        self,
        *,
        connected: bool = True,
        raises_on_connect: bool = False,
        loaded_pages: list[dict[str, object]] | None = None,
        threads: dict[str, dict[str, object]] | None = None,
        notifications: list[dict[str, object]] | None = None,
    ) -> None:
        """Create a fake transport with deterministic responses."""
        self.connected = connected
        self.raises_on_connect = raises_on_connect
        self.loaded_pages = loaded_pages or [{"data": [], "nextCursor": None}]
        self.threads = threads or {}
        self.notifications = notifications or []
        self.calls: list[tuple[str, Mapping[str, object]]] = []
        self.closed = False

    def connect(self) -> bool:
        """Return configured connection state."""
        if self.raises_on_connect:
            raise OSError("connection refused")
        return self.connected

    def call(self, method: str, params: Mapping[str, object]) -> Mapping[str, object] | None:
        """Return fake JSON-RPC responses for selected methods."""
        self.calls.append((method, dict(params)))
        if method == "thread/loaded/list":
            return self.loaded_pages.pop(0)
        if method == "thread/read":
            thread_id = params["threadId"]
            return {"thread": self.threads[str(thread_id)]}
        return {}

    def iter_notifications(self) -> Iterator[Mapping[str, object]]:
        """Yield preloaded notifications."""
        yield from self.notifications

    def close(self) -> None:
        """Mark the fake client closed."""
        self.closed = True


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure PyQt signals have an application object during tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _thread_payload(
    thread_id: str,
    *,
    status: Mapping[str, object] | None = None,
    cwd: str = "D:/work/repo-a",
    name: str | None = None,
) -> dict[str, object]:
    """Build the subset of Thread payload fields used by the connector."""
    return {
        "id": thread_id,
        "cwd": cwd,
        "name": name,
        "preview": "first prompt",
        "status": dict(status or {"type": "idle"}),
    }


def _server_text_frame(text: str, *, opcode: int = 0x1, masked: bool = False) -> bytes:
    """Build a server-to-client WebSocket frame for transport tests."""
    payload = text.encode("utf-8")
    header = bytearray([0x80 | opcode])
    length = len(payload)
    mask_bit = 0x80 if masked else 0
    if length < 126:
        header.append(mask_bit | length)
    elif length <= 0xFFFF:
        header.extend([mask_bit | 126, *struct.pack("!H", length)])
    else:
        header.extend([mask_bit | 127, *struct.pack("!Q", length)])

    if not masked:
        return bytes(header) + payload

    mask = b"\x01\x02\x03\x04"
    masked_payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header) + mask + masked_payload


def _decode_client_payload(frame: bytes) -> bytes:
    """Decode a masked client text frame back into raw payload bytes."""
    length_code = frame[1] & 0x7F
    offset = 2
    if length_code == 126:
        length = struct.unpack("!H", frame[offset : offset + 2])[0]
        offset += 2
    elif length_code == 127:
        length = struct.unpack("!Q", frame[offset : offset + 8])[0]
        offset += 8
    else:
        length = length_code

    mask = frame[offset : offset + 4]
    offset += 4
    payload = frame[offset : offset + length]
    return bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))


def _decode_client_text_frame(frame: bytes) -> dict[str, object]:
    """Decode a masked client text frame back into a JSON object."""
    return json.loads(_decode_client_payload(frame).decode("utf-8"))


def test_handle_notification_updates_registry_and_emits_session_status() -> None:
    """thread/status/changed should update one session and emit aggregate status."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    session_spy = QSignalSpy(connector.session_updated)
    status_spy = QSignalSpy(connector.status_changed)

    connector._handle_notification(
        "thread/status/changed",
        {
            "endpointId": "vscode-main",
            "threadId": "thread-a",
            "status": {"type": "active", "activeFlags": ["waitingOnApproval"]},
        },
    )

    session = registry.get("vscode-main::thread-a")
    assert session is not None
    assert session.status is CodexStatus.WAITING_APPROVAL
    assert session.display_name == "thread-a"
    assert len(session_spy) == 1
    assert isinstance(session_spy[0][0], SessionStatus)
    assert status_spy[0][0] is CodexStatus.WAITING_APPROVAL


def test_subscribe_threads_reads_loaded_thread_list_and_updates_registry() -> None:
    """Loaded thread discovery should read each thread and seed session state."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    fake_client = FakeAppServerClient(
        loaded_pages=[{"data": ["thread-a", "thread-b"], "nextCursor": None}],
        threads={
            "thread-a": _thread_payload(
                "thread-a",
                status={"type": "active", "activeFlags": []},
                cwd="D:/work/repo-a",
            ),
            "thread-b": _thread_payload(
                "thread-b",
                status={"type": "idle"},
                cwd="D:/work/repo-b",
            ),
        },
    )
    connector._client = fake_client
    session_spy = QSignalSpy(connector.session_updated)

    connector._subscribe_threads()

    assert [method for method, _params in fake_client.calls] == [
        "thread/loaded/list",
        "thread/read",
        "thread/read",
    ]
    assert registry.get("ws://127.0.0.1:18731::thread-a").status is CodexStatus.WORKING  # type: ignore[union-attr]
    assert registry.get("ws://127.0.0.1:18731::thread-b").status is CodexStatus.IDLE  # type: ignore[union-attr]
    assert len(session_spy) == 2


def test_session_updated_signal_emits_session_status_object() -> None:
    """Session updates should emit the concrete SessionStatus payload."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    session_spy = QSignalSpy(connector.session_updated)

    connector._handle_thread_started(
        {
            "thread": _thread_payload(
                "thread-a",
                status={"type": "active", "activeFlags": ["waitingOnUserInput"]},
                name="Repo A",
            )
        }
    )

    emitted = session_spy[0][0]
    assert isinstance(emitted, SessionStatus)
    assert emitted.display_name == "Repo A"
    assert emitted.status is CodexStatus.WAITING_USER_INPUT


def test_connect_failure_is_graceful_and_does_not_emit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connection failure should not crash or emit stale statuses."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    fake_client = FakeAppServerClient(connected=False)
    monkeypatch.setattr(connector, "_build_client", lambda: fake_client)
    status_spy = QSignalSpy(connector.status_changed)

    assert connector._connect() is False

    assert fake_client.closed is True
    assert registry.count() == 0
    assert len(status_spy) == 0


def test_connect_failure_from_exception_is_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport exceptions during connect should be swallowed as a failed connection."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    fake_client = FakeAppServerClient(raises_on_connect=True)
    monkeypatch.setattr(connector, "_build_client", lambda: fake_client)

    assert connector._connect() is False
    assert fake_client.closed is True


def test_thread_started_and_closed_update_registry_and_aggregate_status() -> None:
    """Thread lifecycle notifications should add and remove registry sessions."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    status_spy = QSignalSpy(connector.status_changed)

    connector._handle_thread_started(
        {
            "thread": _thread_payload(
                "thread-a",
                status={"type": "active", "activeFlags": []},
                cwd="D:/work/repo-a",
            )
        }
    )
    connector._handle_thread_closed({"threadId": "thread-a"})

    assert registry.count() == 0
    assert [arguments[0] for arguments in status_spy] == [
        CodexStatus.WORKING,
        CodexStatus.OFFLINE,
    ]


def test_connector_uses_five_second_retry_interval() -> None:
    """Failed connections should retry every five seconds in the run loop."""
    assert AppServerConnector.RETRY_INTERVAL_MS == 5000


def test_build_client_selects_websocket_or_unsupported_transport() -> None:
    """Connector should only build WebSocket clients for configured ws endpoints."""
    registry = SessionRegistry()
    ws_connector = AppServerConnector(
        AppConfig(app_server_url="ws://127.0.0.1:18731"),
        registry,
    )
    default_connector = AppServerConnector(AppConfig(), registry)

    ws_client = ws_connector._build_client()
    unsupported_client = default_connector._build_client()

    assert isinstance(ws_client, WebSocketJsonRpcClient)
    assert isinstance(unsupported_client, UnsupportedAppServerClient)
    assert unsupported_client.endpoint_url == "stdio://"
    assert unsupported_client.connect() is False
    assert unsupported_client.call("thread/loaded/list", {}) is None
    assert list(unsupported_client.iter_notifications()) == []
    unsupported_client.close()


def test_connect_success_sets_client_and_close_clears_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful connections should hold the client until explicit close."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    fake_client = FakeAppServerClient()
    monkeypatch.setattr(connector, "_build_client", lambda: fake_client)

    assert connector._connect() is True
    assert connector._client is fake_client

    connector._close_client()

    assert fake_client.closed is True
    assert connector._client is None


def test_subscribe_threads_handles_pagination_and_invalid_responses() -> None:
    """Loaded-thread discovery should page through results and ignore bad payloads."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    paged_client = FakeAppServerClient(
        loaded_pages=[
            {"data": ["thread-a"], "nextCursor": "next-page"},
            {"data": ["thread-b"], "nextCursor": None},
        ],
        threads={
            "thread-a": _thread_payload("thread-a", status={"type": "idle"}),
            "thread-b": _thread_payload("thread-b", status={"type": "systemError"}),
        },
    )
    connector._client = paged_client

    connector._subscribe_threads()

    list_calls = [params for method, params in paged_client.calls if method == "thread/loaded/list"]
    assert list_calls == [
        {"cursor": None, "limit": None},
        {"cursor": "next-page", "limit": None},
    ]
    assert registry.count() == 2

    connector._client = None
    connector._subscribe_threads()
    connector._client = FakeAppServerClient(loaded_pages=[{"data": [1], "nextCursor": None}])
    connector._subscribe_threads()

    class NullResponseClient(FakeAppServerClient):
        """Fake client returning a non-mapping list response."""

        def call(
            self,
            method: str,
            params: Mapping[str, object],
        ) -> Mapping[str, object] | None:
            del method, params
            return None

    connector._client = NullResponseClient()
    connector._subscribe_threads()
    assert registry.count() == 2


def test_invalid_notifications_are_ignored_without_registry_changes() -> None:
    """Schema drift or incomplete notifications should not mutate session state."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)

    connector._handle_notification("thread/started", {})
    connector._handle_notification("thread/closed", {})
    connector._handle_notification("unknown", {"threadId": "thread-a"})
    connector._handle_status_changed({"threadId": "thread-a", "status": "inProgress"})
    connector._handle_status_changed(
        {"threadId": "thread-a", "status": {"type": "active", "activeFlags": ["unknown"]}}
    )
    connector._update_thread_session({"id": "thread-a"}, {})
    connector._update_thread_session(
        {"id": "thread-a", "status": {"type": "active", "activeFlags": ["unknown"]}},
        {},
    )

    class NullReadClient(FakeAppServerClient):
        """Fake client returning no thread/read response."""

        def call(
            self,
            method: str,
            params: Mapping[str, object],
        ) -> Mapping[str, object] | None:
            del method, params
            return None

    connector._read_and_update_thread(NullReadClient(), "missing")

    assert registry.count() == 0


def test_consume_notifications_dispatches_valid_mapping_notifications() -> None:
    """Notification consumption should dispatch only well-formed server notifications."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    connector._client = FakeAppServerClient(
        notifications=[
            {"method": "ignored", "params": {}},
            {"method": 123, "params": {}},
            {"method": "thread/status/changed", "params": "bad"},
            {
                "method": "thread/status/changed",
                "params": {"threadId": "thread-a", "status": {"type": "idle"}},
            },
        ]
    )

    connector._consume_notifications()

    session = registry.get("ws://127.0.0.1:18731::thread-a")
    assert session is not None
    assert session.status is CodexStatus.IDLE


def test_helper_functions_extract_display_names_and_keys() -> None:
    """Pure helper functions should normalize app-server fields deterministically."""
    assert _display_name_from_thread({"name": " Repo A "}, "fallback") == "Repo A"
    assert _display_name_from_thread({"cwd": r"D:\work\repo-b"}, "fallback") == "repo-b"
    assert _display_name_from_thread({"preview": "x" * 30}, "fallback") == "x" * 24
    assert _display_name_from_thread({}, "1234567890123456") == "123456789012"
    assert _extract_string({"a": " ", "b": " value "}, "a", "b") == "value"
    assert _extract_string({"a": 1}, "a") is None
    assert _session_key("endpoint", "thread") == "endpoint::thread"
    assert _is_string_list(["a", "b"]) is True
    assert _is_string_list(["a", 1]) is False
    assert _is_string_list("a") is False
    assert _path_basename("///") == ""


def test_websocket_connect_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WebSocket connect should send an upgrade request and reject non-101 responses."""
    success_socket = FakeSocket([b"HTTP/1.1 101 Switching Protocols\r\n\r\n"])

    def fake_create_connection(
        address: tuple[str, int],
        timeout: float,
    ) -> FakeSocket:
        assert address == ("127.0.0.1", 18731)
        assert timeout == 0.2
        return success_socket

    monkeypatch.setattr(
        "codex_traffic_lights.app_server_connector.socket.create_connection",
        fake_create_connection,
    )
    monkeypatch.setattr(
        "codex_traffic_lights.app_server_connector.os.urandom",
        lambda size: b"\x00" * size,
    )
    client = WebSocketJsonRpcClient("ws://127.0.0.1:18731/rpc?token=abc", timeout_seconds=0.2)

    assert client.connect() is True
    assert success_socket.timeout == 0.2
    assert "GET /rpc?token=abc HTTP/1.1" in success_socket.sent[0].decode("ascii")
    assert WebSocketJsonRpcClient("http://127.0.0.1:18731").connect() is False

    failure_socket = FakeSocket([b"HTTP/1.1 404 Not Found\r\n\r\n"])
    monkeypatch.setattr(
        "codex_traffic_lights.app_server_connector.socket.create_connection",
        lambda _address, timeout: failure_socket,
    )

    assert WebSocketJsonRpcClient("ws://127.0.0.1").connect() is False
    assert failure_socket.closed is True


def test_websocket_call_queues_notifications_and_decodes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON-RPC calls should ignore notifications until the matching response arrives."""
    monkeypatch.setattr(
        "codex_traffic_lights.app_server_connector.os.urandom",
        lambda size: b"\x00" * size,
    )
    notification = {"method": "thread/started", "params": {"threadId": "thread-a"}}
    response = {"id": 1, "result": {"data": ["thread-a"], "nextCursor": None}}
    live_notification = {"method": "thread/closed", "params": {"threadId": "thread-a"}}
    fake_socket = FakeSocket(
        [
            _server_text_frame(json.dumps(notification)),
            _server_text_frame(json.dumps(response)),
            _server_text_frame(json.dumps(live_notification)),
        ]
    )
    client = WebSocketJsonRpcClient("ws://127.0.0.1:18731", timeout_seconds=0.1)
    client._socket = fake_socket  # type: ignore[assignment]

    result = client.call("thread/loaded/list", {})

    assert result == {"data": ["thread-a"], "nextCursor": None}
    assert _decode_client_text_frame(fake_socket.sent[0]) == {
        "method": "thread/loaded/list",
        "id": 1,
        "params": {},
    }
    assert list(client.iter_notifications()) == [notification, live_notification]


def test_websocket_call_returns_none_for_timeout_or_non_mapping_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON-RPC calls should return None for missing or non-object results."""
    monkeypatch.setattr(
        "codex_traffic_lights.app_server_connector.os.urandom",
        lambda size: b"\x00" * size,
    )
    fake_socket = FakeSocket(
        [
            _server_text_frame(json.dumps({"id": 1, "result": ["not", "mapping"]})),
            _server_text_frame(json.dumps({"method": "thread/started", "params": {}})),
        ]
    )
    client = WebSocketJsonRpcClient("ws://127.0.0.1:18731", timeout_seconds=0.01)
    client._socket = fake_socket  # type: ignore[assignment]

    assert client.call("thread/read", {}) is None
    assert client.call("thread/read", {}) is None


def test_websocket_receive_json_handles_bad_payloads() -> None:
    """Bad WebSocket payloads should be ignored instead of crashing the connector."""
    client = WebSocketJsonRpcClient("ws://127.0.0.1:18731")
    client._socket = FakeSocket(  # type: ignore[assignment]
        [_server_text_frame("not-json"), _server_text_frame("[1]")]
    )

    assert client._receive_json() is None
    assert client._receive_json() is None
    client.close()

    with pytest.raises(OSError, match="not connected"):
        client._require_socket()


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"short", id="short"),
        pytest.param(b"x" * 126, id="extended-16"),
        pytest.param(b"x" * 66000, id="extended-64"),
    ],
)
def test_build_client_text_frame_masks_small_and_extended_payloads(
    payload: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client WebSocket frames should be masked for all supported payload lengths."""
    monkeypatch.setattr(
        "codex_traffic_lights.app_server_connector.os.urandom",
        lambda size: b"\x01\x02\x03\x04"[:size],
    )

    frame = _build_client_text_frame(payload)

    assert frame[0] == 0x81
    assert frame[1] & 0x80
    assert _decode_client_payload(frame) == payload


def test_read_server_text_frame_supports_lengths_masks_and_control_frames() -> None:
    """Server frame reader should decode text frames and surface close frames."""
    short_payload = "hello"
    medium_payload = "x" * 126
    large_payload = "x" * 66000

    assert _read_server_text_frame(FakeSocket([_server_text_frame(short_payload)])) == short_payload
    assert _read_server_text_frame(FakeSocket([_server_text_frame(medium_payload)])) == (
        medium_payload
    )
    assert _read_server_text_frame(FakeSocket([_server_text_frame(large_payload)])) == large_payload
    assert _read_server_text_frame(FakeSocket([_server_text_frame("masked", masked=True)])) == (
        "masked"
    )
    assert _read_server_text_frame(FakeSocket([_server_text_frame("binary", opcode=0x2)])) == ""

    with pytest.raises(OSError, match="closed"):
        _read_server_text_frame(FakeSocket([_server_text_frame("", opcode=0x8)]))


def test_recv_helpers_return_exact_bytes_or_raise() -> None:
    """Socket receive helpers should stop on markers and raise on disconnects."""
    assert _recv_until(FakeSocket([b"abc", b"def\r\n\r\n"]), b"\r\n\r\n", 0.1) == (
        b"abcdef\r\n\r\n"
    )
    assert _recv_exact(FakeSocket([b"abc"]), 3) == b"abc"

    with pytest.raises(OSError, match="timed out"):
        _recv_until(FakeSocket([]), b"missing", 0.01)
    with pytest.raises(OSError, match="disconnected"):
        _recv_exact(FakeSocket([]), 1)
