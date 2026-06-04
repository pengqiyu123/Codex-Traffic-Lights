"""Tests for compact multi-session status aggregation."""

from __future__ import annotations

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.status_aggregator import (
    STATUS_PRIORITY,
    aggregate_display_text,
    aggregate_status,
)


def _session(
    status: CodexStatus,
    *,
    endpoint_id: str = "endpoint",
    thread_id: str = "thread",
    display_name: str = "project",
) -> SessionStatus:
    """Create one status-bearing session for aggregation tests."""
    return SessionStatus(
        session_key=f"{endpoint_id}::{thread_id}",
        thread_id=thread_id,
        endpoint_id=endpoint_id,
        display_name=display_name,
        status=status,
        last_updated=100.0,
    )


def test_empty_sessions_aggregate_to_offline() -> None:
    """No tracked sessions should show the application-level offline state."""
    assert aggregate_status([]) is CodexStatus.OFFLINE


def test_single_session_returns_its_status() -> None:
    """A single session should drive the compact global status directly."""
    assert aggregate_status([_session(CodexStatus.WORKING)]) is CodexStatus.WORKING


def test_multiple_sessions_use_highest_priority_status() -> None:
    """Aggregation should prefer urgent states over ordinary work and idle."""
    sessions = [
        _session(CodexStatus.IDLE, endpoint_id="e1", thread_id="t1"),
        _session(CodexStatus.WORKING, endpoint_id="e2", thread_id="t2"),
        _session(CodexStatus.WAITING_APPROVAL, endpoint_id="e3", thread_id="t3"),
        _session(CodexStatus.ERROR, endpoint_id="e4", thread_id="t4"),
    ]

    assert aggregate_status(sessions) is CodexStatus.ERROR


def test_waiting_approval_beats_working_and_idle() -> None:
    """Approval requests should be more visible than ordinary work."""
    sessions = [
        _session(CodexStatus.IDLE, endpoint_id="e1", thread_id="t1"),
        _session(CodexStatus.WORKING, endpoint_id="e2", thread_id="t2"),
        _session(CodexStatus.WAITING_APPROVAL, endpoint_id="e3", thread_id="t3"),
    ]

    assert aggregate_status(sessions) is CodexStatus.WAITING_APPROVAL


def test_all_idle_sessions_aggregate_to_idle() -> None:
    """Idle should be preserved when every tracked session is idle."""
    sessions = [
        _session(CodexStatus.IDLE, endpoint_id="e1", thread_id="t1"),
        _session(CodexStatus.IDLE, endpoint_id="e2", thread_id="t2"),
    ]

    assert aggregate_status(sessions) is CodexStatus.IDLE


def test_aggregate_display_text_for_single_and_multiple_sessions() -> None:
    """Compact text should add session count only for multi-session displays."""
    single = [_session(CodexStatus.WORKING)]
    multiple = [
        _session(CodexStatus.WAITING_APPROVAL, endpoint_id="e1", thread_id="t1"),
        _session(CodexStatus.IDLE, endpoint_id="e2", thread_id="t2"),
        _session(CodexStatus.WORKING, endpoint_id="e3", thread_id="t3"),
    ]

    assert aggregate_display_text(single, CodexStatus.WORKING) == "正在工作"
    assert aggregate_display_text(multiple, CodexStatus.WAITING_APPROVAL) == (
        "待审批确认 · 3 会话"
    )


def test_status_priority_uses_only_current_six_statuses() -> None:
    """Aggregator should not revive obsolete AI-inferred statuses."""
    obsolete_names = {
        "DEEP_WORK",
        "NORMAL_WORK",
        "QUEUED",
        "REVIEW_READY",
        "AWAITING_APPROVAL",
    }

    assert STATUS_PRIORITY == {
        CodexStatus.ERROR: 0,
        CodexStatus.WAITING_APPROVAL: 1,
        CodexStatus.WAITING_USER_INPUT: 2,
        CodexStatus.WORKING: 3,
        CodexStatus.IDLE: 4,
        CodexStatus.OFFLINE: 5,
    }
    assert obsolete_names.isdisjoint({status.name for status in STATUS_PRIORITY})
