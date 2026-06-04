"""Watch real Codex Traffic Lights hook session files.

This script is intentionally read-only. It observes files written by hooks and
prints changes so multi-conversation behavior can be proven before product code
changes.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_SESSIONS_DIR = Path.home() / ".codex-traffic-lights" / "sessions"
KNOWN_STATUSES = {
    "OFFLINE",
    "IDLE",
    "WORKING",
    "WAITING_APPROVAL",
    "WAITING_USER_INPUT",
    "ERROR",
    "NOT_LOADED",
}


@dataclass(frozen=True)
class ObservedSession:
    """One observed hook session snapshot."""

    path: Path
    session_key: str
    status: str
    display_name: str
    updated_at: float
    source: str = "hook-file"

    @property
    def fingerprint(self) -> tuple[str, str, float]:
        """Return values that indicate whether a session changed."""
        return (self.session_key, self.status, self.updated_at)


def load_sessions(sessions_dir: Path = DEFAULT_SESSIONS_DIR) -> list[ObservedSession]:
    """Load valid hook session files from a directory."""
    if not sessions_dir.exists():
        return []

    sessions: list[ObservedSession] = []
    for path in sorted(sessions_dir.glob("*.json")):
        session = load_session_file(path)
        if session is not None:
            sessions.append(session)
    return sorted(sessions, key=lambda item: (item.display_name.casefold(), item.session_key))


def load_session_file(path: Path) -> ObservedSession | None:
    """Parse one hook session file, returning None for invalid content."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    session_key = _string_value(payload, "session_key")
    status = _string_value(payload, "status")
    display_name = _string_value(payload, "display_name")
    updated_at = payload.get("updated_at")
    if not (
        session_key
        and status in KNOWN_STATUSES
        and display_name
        and isinstance(updated_at, int | float)
    ):
        return None

    return ObservedSession(
        path=path,
        session_key=session_key,
        status=status,
        display_name=display_name,
        updated_at=float(updated_at),
    )


def summarize_sessions(sessions: list[ObservedSession]) -> dict[str, Any]:
    """Return a compact JSON-safe summary for reports."""
    return {
        "source": "hook-file",
        "source_count": len(sessions),
        "session_keys": [session.session_key for session in sessions],
        "display_names": [session.display_name for session in sessions],
        "statuses": [session.status for session in sessions],
        "sessions": [
            {
                "file": str(session.path),
                "session_key": session.session_key,
                "display_name": session.display_name,
                "status": session.status,
                "updated_at": session.updated_at,
            }
            for session in sessions
        ],
    }


def watch_sessions(sessions_dir: Path, duration: float, interval: float) -> int:
    """Print session changes for a fixed duration."""
    deadline = time.monotonic() + duration
    previous: dict[str, tuple[str, str, float]] = {}
    printed_any = False

    print(f"watching={sessions_dir}")
    while time.monotonic() <= deadline:
        sessions = load_sessions(sessions_dir)
        current = {session.session_key: session.fingerprint for session in sessions}
        if current != previous:
            print(json.dumps(summarize_sessions(sessions), ensure_ascii=False, indent=2))
            previous = current
            printed_any = True
        time.sleep(interval)

    if not printed_any:
        summary = summarize_sessions(load_sessions(sessions_dir))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    """Run the live watcher CLI."""
    parser = argparse.ArgumentParser(description="Watch real Codex Traffic Lights sessions.")
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    return watch_sessions(args.sessions_dir, args.duration, args.interval)


def _string_value(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


if __name__ == "__main__":
    raise SystemExit(main())
