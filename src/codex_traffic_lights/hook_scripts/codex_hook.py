"""Codex CLI hook entrypoint for the file bridge."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from codex_traffic_lights.hook_bridge import (
    HookEventMapper,
    remove_hook_session,
    write_hook_session,
)


def main(
    argv: list[str] | None = None,
    stdin_text: str | None = None,
    sessions_dir: Path | None = None,
) -> int:
    """Parse one Codex hook event and update the shared session file."""
    args = list(sys.argv[1:] if argv is None else argv)
    payload = _read_payload(stdin_text)
    event_name = args[0] if args else _event_name_from_payload(payload)
    if not event_name:
        return 0

    raw_key = HookEventMapper._extract_session_key(payload)
    session_key = f"codex::{raw_key}"
    if event_name == "SessionEnd":
        remove_hook_session(session_key, sessions_dir)
        return 0

    status = HookEventMapper.map_codex_event(event_name, payload)
    if status is None:
        return 0

    display_name = HookEventMapper.extract_display_name(payload, raw_key)
    write_hook_session(
        session_key=session_key,
        status=status,
        display_name=display_name,
        sessions_dir=sessions_dir,
    )
    return 0


def _read_payload(stdin_text: str | None) -> dict[str, object]:
    """Read hook payload JSON from stdin or a supplied test string."""
    raw = stdin_text
    if raw is None:
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _event_name_from_payload(payload: dict[str, object]) -> str:
    """Extract a hook event name from common payload fields."""
    for key in ("event_name", "hook_event_name", "event", "type"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
