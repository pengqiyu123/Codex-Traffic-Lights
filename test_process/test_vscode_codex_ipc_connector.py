"""Tests for the VSCode Codex IPC connector prototype."""

from __future__ import annotations

import json

from vscode_codex_ipc_connector import (
    ConversationStore,
    FrameDecoder,
    IpcConnectorConfig,
    build_initialize_request,
    encode_frame,
    run_connector,
    summarize_ipc_message,
)


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


def test_build_initialize_request_uses_probe_client_type() -> None:
    """The connector should register as a temporary observer client."""
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
    assert "local" not in json.dumps(data)


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
                "patches": [{"op": "replace", "path": ["turns", 0, "status"], "value": "completed"}],
            },
        ),
        store,
    )

    assert transcript is not None
    assert transcript.last_turn_status == "completed"
    assert transcript.product_status == "IDLE"


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
                        "value": {"type": "codex/event/request_user_input", "text": "secret question"},
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


def test_run_connector_reconnects_after_disconnect_and_outputs_json_lines() -> None:
    """The CLI loop should reconnect after a broken pipe and continue reading."""
    stream_factory = FlakyStreamFactory()
    output: list[str] = []

    exit_code = run_connector(
        IpcConnectorConfig(duration=1.0, max_events=1, reconnect_delay=0.01),
        stream_factory=stream_factory,
        write_line=output.append,
    )

    assert exit_code == 0
    assert stream_factory.calls == 2
    assert len(output) == 1
    assert json.loads(output[0])["productStatus"] == "WORKING"


class FlakyStreamFactory:
    """Raise once, then return a stream with one status broadcast."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> "MemoryStream":
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


class MemoryStream:
    """In-memory framed IPC stream for connector loop tests."""

    def __init__(self, messages: list[dict[str, object]]) -> None:
        self._chunks = bytearray(b"".join(encode_frame(message) for message in messages))
        self.writes: list[bytes] = []
        self.closed = False

    def write_all(self, data: bytes) -> None:
        self.writes.append(data)

    def read_exact(self, size: int, timeout: float) -> bytes:
        del timeout
        if not self._chunks:
            raise OSError("disconnected")
        result = self._chunks[:size]
        del self._chunks[:size]
        return bytes(result)

    def close(self) -> None:
        self.closed = True


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
            "type": "thread-stream-state-changed",
            "version": 7,
            "change": change,
        },
    }
