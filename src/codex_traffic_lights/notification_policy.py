"""Pure notification transition rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionStatus

_COMPLETION_SOURCE_STATES = frozenset(
    (
        CodexStatus.WORKING,
        CodexStatus.WAITING_APPROVAL,
        CodexStatus.WAITING_USER_INPUT,
    )
)


class AlertKind(Enum):
    """User-facing alert event categories."""

    COMPLETED = "completed"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_USER_INPUT = "waiting_user_input"
    ERROR = "error"


@dataclass(frozen=True)
class SessionAlert:
    """One session event that warrants user attention."""

    kind: AlertKind
    session_key: str
    display_name: str
    old_status: CodexStatus | None
    new_status: CodexStatus


def compute_alerts(
    prev: dict[str, CodexStatus],
    current: list[SessionStatus],
    initialized: bool,
) -> list[SessionAlert]:
    """Return transitions that warrant user attention."""
    if not initialized:
        return []

    alerts: list[SessionAlert] = []
    for session in current:
        old_status = prev.get(session.session_key)
        if old_status is session.status:
            continue
        kind = _alert_kind(old_status, session.status)
        if kind is not None:
            alerts.append(
                SessionAlert(
                    kind=kind,
                    session_key=session.session_key,
                    display_name=session.display_name,
                    old_status=old_status,
                    new_status=session.status,
                )
            )
    return alerts


def _alert_kind(
    old_status: CodexStatus | None,
    new_status: CodexStatus,
) -> AlertKind | None:
    """Classify one status transition into a user-facing alert event."""
    if new_status is CodexStatus.IDLE and old_status in _COMPLETION_SOURCE_STATES:
        return AlertKind.COMPLETED
    if new_status is CodexStatus.WAITING_APPROVAL:
        return AlertKind.WAITING_APPROVAL
    if new_status is CodexStatus.WAITING_USER_INPUT:
        return AlertKind.WAITING_USER_INPUT
    if new_status is CodexStatus.ERROR:
        return AlertKind.ERROR
    return None
