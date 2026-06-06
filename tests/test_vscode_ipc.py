"""Tests for the product VSCode Codex IPC connector."""

from __future__ import annotations

import json
import time

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.session_models import SessionRegistry, SessionStatus
from codex_traffic_lights.vscode_ipc import (
    ConversationStore,
    FrameDecoder,
    IpcReadTimeoutError,
    VSCodeIpcConnector,
    _product_status,
    _safe_display_name,
    build_initialize_request,
    encode_frame,
    summarize_ipc_message,
)


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure PyQt signals have an application object during tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_frame_decoder_handles_split_length_prefixed_frames() -> None:
    """The IPC frame parser should handle arbitrary chunk boundaries."""
    decoder = FrameDecoder()
    first = {"type": "response", "method": "initialize"}
    second = {"type": "broadcast", "method": "thread-stream-state-changed"}
    payload = encode_frame(first) + encode_frame(second)

    decoded = decoder.feed(payload[:3])
    decoded += decoder.feed(payload[3:9])
    decoded += decoder.feed(payload[9:])

    assert decoded == [first, second]


def test_build_initialize_request_uses_product_client_type() -> None:
    """The connector should register as a traffic-light observer client."""
    request = build_initialize_request()

    assert request["type"] == "request"
    assert request["method"] == "initialize"
    assert request["sourceClientId"] == "initializing-client"
    assert request["params"] == {"clientType": "traffic-lights-connector"}


def test_snapshot_extracts_last_turn_status_without_sensitive_text() -> None:
    """Snapshot output must include status fields but omit prompt and generated text."""
    store = ConversationStore()
    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "snapshot",
                "revision": 10,
                "conversationState": {
                    "id": "thread-a",
                    "hostId": "local",
                    "turns": [
                        {
                            "status": "inProgress",
                            "params": {
                                "threadId": "thread-a",
                                "input": [{"type": "text", "text": "secret prompt"}],
                            },
                            "items": [
                                {"type": "agentMessage", "text": "secret generated answer"},
                            ],
                            "hookRuns": [{"id": r"contains\local\path"}],
                        }
                    ],
                },
            },
        ),
        store,
    )

    assert transcript is not None
    data = transcript.to_json_dict()
    assert data["conversationId"] == "thread-a"
    assert data["revision"] == 10
    assert data["lastTurn"]["status"] == "inProgress"
    assert data["productStatus"] == "WORKING"
    assert "secret" not in json.dumps(data)
    assert r"contains\local\path" not in json.dumps(data)


def test_patch_updates_last_turn_status_to_completed() -> None:
    """JSON patches should update stored turn summaries."""
    store = ConversationStore()
    summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "snapshot",
                "revision": 1,
                "conversationState": {
                    "id": "thread-a",
                    "turns": [{"status": "inProgress", "params": {"threadId": "thread-a"}}],
                },
            },
        ),
        store,
    )

    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "patches",
                "baseRevision": 1,
                "revision": 2,
                "patches": [
                    {"op": "replace", "path": ["turns", 0, "status"], "value": "completed"}
                ],
            },
        ),
        store,
    )

    assert transcript is not None
    assert transcript.last_turn_status == "completed"
    assert transcript.product_status is CodexStatus.IDLE


@pytest.mark.parametrize(
    ("last_turn_status", "approval", "user_input", "expected"),
    [
        ("inProgress", (), (), CodexStatus.WORKING),
        ("completed", (), (), CodexStatus.IDLE),
        ("failed", (), (), CodexStatus.ERROR),
        (
            "inProgress",
            ("type:codex/event/exec_approval_request",),
            (),
            CodexStatus.WAITING_APPROVAL,
        ),
        (
            "inProgress",
            (),
            ("type:codex/event/request_user_input",),
            CodexStatus.WAITING_USER_INPUT,
        ),
        (None, (), (), CodexStatus.OFFLINE),
    ],
)
def test_product_status_maps_all_six_product_states(
    last_turn_status: str | None,
    approval: tuple[str, ...],
    user_input: tuple[str, ...],
    expected: CodexStatus,
) -> None:
    """The transcript mapping should cover the six product statuses."""
    assert _product_status(last_turn_status, list(approval), list(user_input)) is expected


def test_recent_in_progress_status_stays_working() -> None:
    """A fresh inProgress turn should remain WORKING."""
    now_ms = 1_700_000_000_000
    started_at_ms = now_ms - 10_000

    status = _product_status("inProgress", [], [], started_at_ms, now_ms)

    assert status is CodexStatus.WORKING


def test_old_in_progress_status_stays_working_without_runtime_idle() -> None:
    """Long-running active turns should keep WORKING instead of timing out to IDLE."""
    now_ms = 1_700_000_000_000
    started_at_ms = now_ms - 600_000

    status = _product_status("inProgress", [], [], started_at_ms, now_ms)

    assert status is CodexStatus.WORKING


def test_snapshot_runtime_idle_overrides_stale_in_progress_turn() -> None:
    """Runtime idle status should beat an old residual inProgress turn."""
    store = ConversationStore()

    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "snapshot",
                "revision": 1,
                "conversationState": {
                    "id": "thread-a",
                    "threadRuntimeStatus": {"type": "idle"},
                    "turns": [
                        {
                            "status": "inProgress",
                            "turnStartedAtMs": int((time.time() - 600.0) * 1000),
                            "params": {"threadId": "thread-a"},
                        }
                    ],
                },
            },
        ),
        store,
    )

    assert transcript is not None
    assert transcript.last_turn_status == "inProgress"
    assert transcript.product_status is CodexStatus.IDLE


def test_snapshot_runtime_active_with_empty_flags_stays_working_for_long_task() -> None:
    """Runtime active status should preserve WORKING for long tasks."""
    store = ConversationStore()

    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "snapshot",
                "revision": 1,
                "conversationState": {
                    "id": "thread-a",
                    "threadRuntimeStatus": {"type": "active", "activeFlags": []},
                    "turns": [
                        {
                            "status": "inProgress",
                            "turnStartedAtMs": int((time.time() - 3_600.0) * 1000),
                            "params": {"threadId": "thread-a"},
                        }
                    ],
                },
            },
        ),
        store,
    )

    assert transcript is not None
    assert transcript.product_status is CodexStatus.WORKING


@pytest.mark.parametrize(
    ("active_flags", "expected"),
    [
        (["waitingOnApproval"], CodexStatus.WAITING_APPROVAL),
        (["waitingOnUserInput"], CodexStatus.WAITING_USER_INPUT),
    ],
)
def test_runtime_active_flags_map_waiting_statuses(
    active_flags: list[str],
    expected: CodexStatus,
) -> None:
    """Runtime activeFlags should drive waiting states when VSCode exposes them."""
    store = ConversationStore()

    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "snapshot",
                "revision": 1,
                "conversationState": {
                    "id": "thread-a",
                    "threadRuntimeStatus": {"type": "active", "activeFlags": active_flags},
                    "turns": [{"status": "inProgress", "params": {"threadId": "thread-a"}}],
                },
            },
        ),
        store,
    )

    assert transcript is not None
    assert transcript.product_status is expected


def test_snapshot_detects_waiting_signals_without_recording_item_payloads() -> None:
    """Starting during a wait state should still see sanitized item type signals."""
    store = ConversationStore()

    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "snapshot",
                "revision": 10,
                "conversationState": {
                    "id": "thread-a",
                    "turns": [
                        {
                            "status": "inProgress",
                            "params": {"threadId": "thread-a"},
                            "items": [
                                {
                                    "type": "codex/event/exec_approval_request",
                                    "command": r"write C:\Users\secret\file.txt",
                                }
                            ],
                        }
                    ],
                },
            },
        ),
        store,
    )

    assert transcript is not None
    data = transcript.to_json_dict()
    assert data["productStatus"] == "WAITING_APPROVAL"
    assert data["approvalSignals"] == ["type:codex/event/exec_approval_request"]
    assert data["signalPatchPaths"] == ["/turns/0/items/0"]
    assert "secret" not in json.dumps(data)
    assert "command" not in json.dumps(data)


def test_patch_without_known_status_or_signal_is_not_emitted() -> None:
    """A patch-only update must not be misreported as OFFLINE."""
    store = ConversationStore()

    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "patches",
                "baseRevision": 1,
                "revision": 2,
                "patches": [{"op": "add", "path": ["turns", 64, "items", 0], "value": {}}],
            },
        ),
        store,
    )

    assert transcript is None


def test_patch_detects_approval_signal_without_recording_patch_value() -> None:
    """Approval request payloads should become WAITING_APPROVAL without leaking command text."""
    store = ConversationStore()
    _seed_in_progress(store)

    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "patches",
                "baseRevision": 1,
                "revision": 2,
                "patches": [
                    {
                        "op": "add",
                        "path": ["turns", 0, "items", 0],
                        "value": {
                            "type": "codex/event/exec_approval_request",
                            "command": r"write C:\Users\secret\file.txt",
                        },
                    }
                ],
            },
        ),
        store,
    )

    assert transcript is not None
    data = transcript.to_json_dict()
    assert data["productStatus"] == "WAITING_APPROVAL"
    assert data["approvalSignals"] == ["type:codex/event/exec_approval_request"]
    assert data["signalPatchPaths"] == ["/turns/0/items/0"]
    assert "secret" not in json.dumps(data)
    assert "command" not in json.dumps(data)


def test_patch_detects_user_input_signal() -> None:
    """User input request payloads should become WAITING_USER_INPUT."""
    store = ConversationStore()
    _seed_in_progress(store)

    transcript = summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "patches",
                "baseRevision": 1,
                "revision": 2,
                "patches": [
                    {
                        "op": "add",
                        "path": ["turns", 0, "items", 1],
                        "value": {
                            "type": "codex/event/request_user_input",
                            "text": "secret question",
                        },
                    }
                ],
            },
        ),
        store,
    )

    assert transcript is not None
    data = transcript.to_json_dict()
    assert data["productStatus"] == "WAITING_USER_INPUT"
    assert data["userInputSignals"] == ["type:codex/event/request_user_input"]
    assert "secret question" not in json.dumps(data)


def test_connector_updates_registry_and_emits_session_signals() -> None:
    """A status transcript should update shared SessionRegistry and emit UI signals."""
    registry = SessionRegistry()
    connector = VSCodeIpcConnector(AppConfig(), registry)
    session_spy = QSignalSpy(connector.session_updated)
    sessions_spy = QSignalSpy(connector.sessions_changed)
    status_spy = QSignalSpy(connector.status_changed)

    connector._handle_transcript(  # noqa: SLF001
        _transcript("thread-a", "local", 1, CodexStatus.WORKING, "inProgress")
    )

    session = registry.get("vscode-ipc::thread-a")
    assert session is not None
    assert session.status is CodexStatus.WORKING
    assert session.display_name == "thread-a"
    assert len(session_spy) == 1
    assert isinstance(session_spy[0][0], SessionStatus)
    assert sessions_spy[0][0] == [session]
    assert status_spy[0][0] is CodexStatus.WORKING


def test_snapshot_display_name_uses_safe_metadata_before_thread_id() -> None:
    """Known safe metadata should produce readable names instead of opaque ids."""
    store = ConversationStore()
    transcript = summarize_ipc_message(
        _broadcast(
            "019e8825-161c-7e71-8fda-699303315443",
            {
                "type": "snapshot",
                "revision": 1,
                "conversationState": {
                    "id": "019e8825-161c-7e71-8fda-699303315443",
                    "title": "Code Light",
                    "turns": [{"status": "completed"}],
                },
            },
        ),
        store,
    )

    assert transcript is not None
    assert transcript.display_name == "Code Light"


def test_safe_display_name_shortens_opaque_conversation_ids() -> None:
    """UUID-like ids should be converted to a small session label."""
    assert _safe_display_name("019e8825-161c-7e71-8fda-699303315443", None) == "会话 443"


def test_connector_does_not_expire_long_running_working_sessions_to_idle() -> None:
    """A long-running active IPC session should not be timed out to IDLE."""
    registry = SessionRegistry()
    connector = VSCodeIpcConnector(AppConfig(), registry)
    status_spy = QSignalSpy(connector.status_changed)

    connector._handle_transcript(  # noqa: SLF001
        _transcript("thread-a", "local", 1, CodexStatus.WORKING, "inProgress")
    )
    connector._expire_stale_working_sessions(now=time.time() + 999.0)  # noqa: SLF001

    session = registry.get("vscode-ipc::thread-a")
    assert session is not None
    assert session.status is CodexStatus.WORKING
    assert [arguments[0] for arguments in status_spy] == [CodexStatus.WORKING]


def test_connector_reconnects_after_disconnect_and_emits_status() -> None:
    """The connector loop should reconnect after a broken pipe and continue reading."""
    registry = SessionRegistry()
    stream_factory = FlakyStreamFactory()
    connector = VSCodeIpcConnector(
        AppConfig(vscode_ipc_reconnect_delay=0.01),
        registry,
        stream_factory=stream_factory,
    )
    status_spy = QSignalSpy(connector.status_changed)

    connector._run_loop(duration=1.0, max_events=1)  # noqa: SLF001

    assert stream_factory.calls == 2
    assert status_spy[0][0] is CodexStatus.WORKING


def test_connector_keeps_connection_open_after_read_timeout() -> None:
    """A quiet pipe should not force reconnect; only real disconnects should."""
    registry = SessionRegistry()
    stream_factory = TimeoutThenMessageStreamFactory()
    connector = VSCodeIpcConnector(
        AppConfig(vscode_ipc_reconnect_delay=0.01, vscode_ipc_read_timeout=0.01),
        registry,
        stream_factory=stream_factory,
    )

    connector._run_loop(duration=1.0, max_events=1)  # noqa: SLF001

    assert stream_factory.calls == 1
    assert registry.get("vscode-ipc::thread-a").status is CodexStatus.WORKING  # type: ignore[union-attr]


def test_connector_respects_disabled_config() -> None:
    """Disabled IPC config should avoid opening the named pipe."""
    stream_factory = FlakyStreamFactory()
    connector = VSCodeIpcConnector(
        AppConfig(vscode_ipc_enabled=False),
        SessionRegistry(),
        stream_factory=stream_factory,
    )

    connector._run_loop(duration=1.0, max_events=1)  # noqa: SLF001

    assert stream_factory.calls == 0


class FlakyStreamFactory:
    """Raise once, then return a stream with one status broadcast."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> MemoryStream:
        self.calls += 1
        if self.calls == 1:
            raise OSError("pipe not ready")
        return MemoryStream(
            [
                {"type": "response", "method": "initialize", "resultType": "success"},
                _broadcast(
                    "thread-a",
                    {
                        "type": "snapshot",
                        "revision": 1,
                        "conversationState": {
                            "id": "thread-a",
                            "turns": [
                                {"status": "inProgress", "params": {"threadId": "thread-a"}}
                            ],
                        },
                    },
                ),
            ]
        )


class TimeoutThenMessageStreamFactory:
    """Return one stream that times out once before delivering messages."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> TimeoutThenMessageStream:
        self.calls += 1
        return TimeoutThenMessageStream(
            [
                {"type": "response", "method": "initialize", "resultType": "success"},
                _broadcast(
                    "thread-a",
                    {
                        "type": "snapshot",
                        "revision": 1,
                        "conversationState": {
                            "id": "thread-a",
                            "turns": [
                                {"status": "inProgress", "params": {"threadId": "thread-a"}}
                            ],
                        },
                    },
                ),
            ]
        )


class MemoryStream:
    """In-memory framed IPC stream for connector loop tests."""

    def __init__(self, messages: list[dict[str, object]]) -> None:
        self._buffer = bytearray(b"".join(encode_frame(message) for message in messages))
        self.writes: list[bytes] = []
        self.closed = False

    def write_all(self, data: bytes) -> None:
        """Record bytes written by the connector."""
        self.writes.append(data)

    def read_exact(self, size: int, timeout: float) -> bytes:
        """Return bytes from the in-memory frame buffer."""
        del timeout
        if not self._buffer:
            raise OSError("pipe closed")
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk

    def close(self) -> None:
        """Mark the stream closed."""
        self.closed = True


class TimeoutThenMessageStream(MemoryStream):
    """In-memory stream that raises one timeout before sending bytes."""

    def __init__(self, messages: list[dict[str, object]]) -> None:
        super().__init__(messages)
        self._timed_out = False

    def read_exact(self, size: int, timeout: float) -> bytes:
        """Raise one read timeout, then delegate to the in-memory stream."""
        if not self._timed_out:
            self._timed_out = True
            raise IpcReadTimeoutError("quiet pipe")
        return super().read_exact(size, timeout)


def _seed_in_progress(store: ConversationStore) -> None:
    summarize_ipc_message(
        _broadcast(
            "thread-a",
            {
                "type": "snapshot",
                "revision": 1,
                "conversationState": {
                    "id": "thread-a",
                    "turns": [{"status": "inProgress", "params": {"threadId": "thread-a"}}],
                },
            },
        ),
        store,
    )


def _broadcast(conversation_id: str, change: dict[str, object]) -> dict[str, object]:
    return {
        "type": "broadcast",
        "method": "thread-stream-state-changed",
        "params": {
            "conversationId": conversation_id,
            "hostId": "local",
            "change": change,
        },
    }


def _transcript(
    conversation_id: str,
    host_id: str,
    revision: int,
    product_status: CodexStatus,
    last_turn_status: str,
    last_turn_started_at_ms: int | None = None,
) -> object:
    from codex_traffic_lights.vscode_ipc import StatusTranscript

    return StatusTranscript(
        conversation_id=conversation_id,
        revision=revision,
        host_id=host_id,
        display_name=None,
        runtime_status_type=None,
        active_flags=(),
        last_turn_status=last_turn_status,
        last_turn_started_at_ms=last_turn_started_at_ms,
        product_status=product_status,
        turn_count=1,
    )
