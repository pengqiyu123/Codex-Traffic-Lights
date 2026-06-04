"""Tests for multi-session data models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionRegistry, SessionStatus


def _session(
    *,
    endpoint_id: str = "endpoint-a",
    thread_id: str = "thread-123456",
    display_name: str = "project-a",
    status: CodexStatus = CodexStatus.WORKING,
    last_updated: float = 100.0,
) -> SessionStatus:
    """Create a SessionStatus with the product session-key format."""
    return SessionStatus(
        session_key=f"{endpoint_id}::{thread_id}",
        thread_id=thread_id,
        endpoint_id=endpoint_id,
        display_name=display_name,
        status=status,
        last_updated=last_updated,
    )


def test_session_status_is_frozen() -> None:
    """SessionStatus should be immutable after creation."""
    session = _session()

    with pytest.raises(FrozenInstanceError):
        session.status = CodexStatus.IDLE


def test_session_key_uses_endpoint_thread_separator() -> None:
    """Session keys should be stable endpoint/thread compound keys."""
    session = _session(endpoint_id="app-server-1", thread_id="thread-abc")

    assert session.session_key == "app-server-1::thread-abc"
    assert session.session_key.split("::") == [session.endpoint_id, session.thread_id]


def test_registry_add_update_remove_get_all_count_and_get() -> None:
    """SessionRegistry should expose the full lifecycle for tracked sessions."""
    registry = SessionRegistry()
    first = _session(display_name="alpha", status=CodexStatus.WORKING)
    updated = _session(display_name="alpha", status=CodexStatus.WAITING_APPROVAL)
    second = _session(
        endpoint_id="endpoint-b",
        thread_id="thread-222",
        display_name="beta",
        status=CodexStatus.IDLE,
    )

    registry.update(first)
    registry.update(second)

    assert registry.count() == 2
    assert registry.get(first.session_key) == first

    registry.update(updated)

    assert registry.count() == 2
    assert registry.get(first.session_key) == updated
    assert registry.get_all() == [updated, second]

    registry.remove(updated.session_key)

    assert registry.count() == 1
    assert registry.get(updated.session_key) is None
    assert registry.get_all() == [second]


def test_registry_get_all_sorts_by_display_name() -> None:
    """Registry output should be stable for expanded multi-session UI rows."""
    registry = SessionRegistry()
    zeta = _session(endpoint_id="e1", thread_id="t1", display_name="zeta")
    alpha = _session(endpoint_id="e2", thread_id="t2", display_name="alpha")
    beta = _session(endpoint_id="e3", thread_id="t3", display_name="beta")

    registry.update(zeta)
    registry.update(alpha)
    registry.update(beta)

    assert [session.display_name for session in registry.get_all()] == [
        "alpha",
        "beta",
        "zeta",
    ]
