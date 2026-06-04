"""Pure Python aggregation helpers for compact multi-session status display."""

from __future__ import annotations

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionStatus

STATUS_PRIORITY: dict[CodexStatus, int] = {
    CodexStatus.ERROR: 0,
    CodexStatus.WAITING_APPROVAL: 1,
    CodexStatus.WAITING_USER_INPUT: 2,
    CodexStatus.WORKING: 3,
    CodexStatus.IDLE: 4,
    CodexStatus.OFFLINE: 5,
}


def aggregate_status(sessions: list[SessionStatus]) -> CodexStatus:
    """Return the highest-priority product status across tracked sessions."""
    if not sessions:
        return CodexStatus.OFFLINE
    return min(sessions, key=lambda session: STATUS_PRIORITY[session.status]).status


def aggregate_display_text(sessions: list[SessionStatus], status: CodexStatus) -> str:
    """Return compact status text for the current aggregate status."""
    if len(sessions) <= 1:
        return status.label
    return f"{status.label} · {len(sessions)} 会话"
