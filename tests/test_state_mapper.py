"""Tests for Codex app-server schema to product-status mapping."""

from collections.abc import Mapping

import pytest

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.state_mapper import CodexStateMapper

OBSOLETE_STATUS_NAMES = {
    "DEEP_WORK",
    "NORMAL_WORK",
    "QUEUED",
    "REVIEW_READY",
    "AWAITING_APPROVAL",
}


@pytest.mark.parametrize(
    ("thread_status", "expected_status"),
    [
        ({"type": "notLoaded"}, None),
        ({"type": "idle"}, CodexStatus.IDLE),
        ({"type": "systemError"}, CodexStatus.ERROR),
        ({"type": "active", "activeFlags": []}, CodexStatus.WORKING),
    ],
)
def test_map_thread_status_covers_all_thread_status_types(
    thread_status: Mapping[str, object],
    expected_status: CodexStatus | None,
) -> None:
    """ThreadStatus.type should map only confirmed Codex states."""
    assert CodexStateMapper.map_thread_status(thread_status) is expected_status


@pytest.mark.parametrize(
    ("active_flags", "expected_status"),
    [
        (["waitingOnApproval"], CodexStatus.WAITING_APPROVAL),
        (["waitingOnUserInput"], CodexStatus.WAITING_USER_INPUT),
    ],
)
def test_map_thread_status_covers_waiting_active_flags(
    active_flags: list[str],
    expected_status: CodexStatus,
) -> None:
    """Known activeFlags should map to their waiting product statuses."""
    thread_status: Mapping[str, object] = {
        "type": "active",
        "activeFlags": active_flags,
    }

    assert CodexStateMapper.map_thread_status(thread_status) is expected_status


@pytest.mark.parametrize(
    ("turn_status", "expected_status"),
    [
        ("inProgress", CodexStatus.WORKING),
        ("failed", CodexStatus.ERROR),
        ("completed", None),
        ("interrupted", None),
    ],
)
def test_map_turn_status_covers_all_turn_status_values(
    turn_status: str,
    expected_status: CodexStatus | None,
) -> None:
    """TurnStatus should not force idle after completion or interruption."""
    assert CodexStateMapper.map_turn_status(turn_status) is expected_status


@pytest.mark.parametrize(
    ("event", "expected_status"),
    [
        ({"status": {"type": "idle"}}, CodexStatus.IDLE),
        (
            {"status": {"type": "active", "activeFlags": ["waitingOnApproval"]}},
            CodexStatus.WAITING_APPROVAL,
        ),
        ({"status": "inProgress"}, CodexStatus.WORKING),
        ({"status": "completed"}, None),
    ],
)
def test_map_event_uses_nested_thread_or_turn_status(
    event: Mapping[str, object],
    expected_status: CodexStatus | None,
) -> None:
    """App-server events should map through their status payload."""
    assert CodexStateMapper.map_event(event) is expected_status


@pytest.mark.parametrize(
    "thread_status",
    [
        {},
        {"type": "unknown"},
        {"type": 123},
        {"type": "active"},
        {"type": "active", "activeFlags": "waitingOnApproval"},
        {"type": "active", "activeFlags": ["unknownFlag"]},
    ],
)
def test_map_thread_status_returns_none_for_unknown_or_bad_input(
    thread_status: Mapping[str, object],
) -> None:
    """Unknown or malformed ThreadStatus payloads should not invent states."""
    assert CodexStateMapper.map_thread_status(thread_status) is None


@pytest.mark.parametrize("turn_status", ["queued", "reviewReady", "", "normalWork"])
def test_map_turn_status_returns_none_for_unknown_input(turn_status: str) -> None:
    """Unknown TurnStatus values should not become product statuses."""
    assert CodexStateMapper.map_turn_status(turn_status) is None


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"status": 123},
        {"status": {"type": "active", "activeFlags": "bad"}},
        {"payload": {"status": "inProgress"}},
    ],
)
def test_map_event_returns_none_for_unknown_or_bad_input(
    event: Mapping[str, object],
) -> None:
    """Unknown or malformed events should be ignored."""
    assert CodexStateMapper.map_event(event) is None


def test_mapper_never_outputs_obsolete_ai_inferred_statuses() -> None:
    """Deprecated eight-state guesses must never be emitted by the mapper."""
    mapped_statuses = {
        status
        for status in [
            CodexStateMapper.map_thread_status({"type": "idle"}),
            CodexStateMapper.map_thread_status(
                {"type": "active", "activeFlags": ["waitingOnApproval"]}
            ),
            CodexStateMapper.map_thread_status(
                {"type": "active", "activeFlags": ["waitingOnUserInput"]}
            ),
            CodexStateMapper.map_thread_status({"type": "active", "activeFlags": []}),
            CodexStateMapper.map_thread_status({"type": "systemError"}),
            CodexStateMapper.map_turn_status("inProgress"),
            CodexStateMapper.map_turn_status("failed"),
        ]
        if status is not None
    }

    assert {status.name for status in mapped_statuses}.isdisjoint(OBSOLETE_STATUS_NAMES)
