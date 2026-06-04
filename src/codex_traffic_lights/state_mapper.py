"""Pure mapping from Codex app-server status payloads to product statuses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeGuard, cast

from codex_traffic_lights.models import CodexStatus

APPROVAL_FLAG = "waitingOnApproval"
USER_INPUT_FLAG = "waitingOnUserInput"


class CodexStateMapper:
    """Map audited Codex app-server schema values into CodexStatus."""

    @staticmethod
    def map_thread_status(status: Mapping[str, object]) -> CodexStatus | None:
        """Map a ThreadStatus payload to a product status."""
        status_type = status.get("type")

        if status_type == "idle":
            return CodexStatus.IDLE
        if status_type == "systemError":
            return CodexStatus.ERROR
        if status_type != "active":
            return None

        active_flags = status.get("activeFlags")
        if not _is_string_sequence(active_flags):
            return None

        flags = set(active_flags)
        if APPROVAL_FLAG in flags:
            return CodexStatus.WAITING_APPROVAL
        if USER_INPUT_FLAG in flags:
            return CodexStatus.WAITING_USER_INPUT
        if not flags:
            return CodexStatus.WORKING
        return None

    @staticmethod
    def map_turn_status(status: str) -> CodexStatus | None:
        """Map a TurnStatus value to a product status, if it should change UI state."""
        if status == "inProgress":
            return CodexStatus.WORKING
        if status == "failed":
            return CodexStatus.ERROR
        return None

    @staticmethod
    def map_event(event: Mapping[str, object]) -> CodexStatus | None:
        """Map an app-server event containing a status payload."""
        status = event.get("status")
        if isinstance(status, str):
            return CodexStateMapper.map_turn_status(status)
        if isinstance(status, Mapping):
            return CodexStateMapper.map_thread_status(cast(Mapping[str, object], status))
        return None


def _is_string_sequence(value: object) -> TypeGuard[Sequence[str]]:
    """Return True when a value is a non-string sequence of strings."""
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str | bytes)
        and all(isinstance(item, str) for item in value)
    )
