"""Pure Python data models for tracked Codex sessions."""

from __future__ import annotations

from dataclasses import dataclass, field

from codex_traffic_lights.models import CodexStatus


@dataclass(frozen=True)
class SessionStatus:
    """Status snapshot for one Codex thread from one endpoint."""

    session_key: str
    thread_id: str
    endpoint_id: str
    display_name: str
    status: CodexStatus
    last_updated: float


@dataclass
class SessionRegistry:
    """In-memory registry for the latest status of every tracked session."""

    _sessions: dict[str, SessionStatus] = field(default_factory=dict)

    def update(self, session: SessionStatus) -> None:
        """Add a new session or replace the existing snapshot for its key."""
        self._sessions[session.session_key] = session

    def remove(self, session_key: str) -> None:
        """Remove a session by key, ignoring unknown keys."""
        self._sessions.pop(session_key, None)

    def get_all(self) -> list[SessionStatus]:
        """Return all sessions sorted by display name for stable UI rows."""
        return sorted(
            self._sessions.values(),
            key=lambda session: (
                session.display_name.casefold(),
                session.endpoint_id.casefold(),
                session.thread_id.casefold(),
            ),
        )

    def get(self, session_key: str) -> SessionStatus | None:
        """Return the session snapshot for a key, if present."""
        return self._sessions.get(session_key)

    def count(self) -> int:
        """Return the number of tracked sessions."""
        return len(self._sessions)
