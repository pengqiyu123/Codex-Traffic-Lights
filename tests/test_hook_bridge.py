"""Tests for hook event mapping."""

from __future__ import annotations

import pytest

from codex_traffic_lights.hook_bridge import HookEventMapper
from codex_traffic_lights.models import CodexStatus


@pytest.mark.parametrize(
    ("event_name", "payload", "expected"),
    [
        ("SessionStart", {}, CodexStatus.IDLE),
        ("UserPromptSubmit", {}, CodexStatus.WORKING),
        ("PreToolUse", {}, CodexStatus.WORKING),
        ("PostToolUse", {}, CodexStatus.WORKING),
        ("PermissionRequest", {}, CodexStatus.WAITING_APPROVAL),
        ("PostToolUseFailure", {}, CodexStatus.ERROR),
        ("Stop", {"status": "error"}, CodexStatus.ERROR),
        ("Stop", {"exit_code": 1}, CodexStatus.ERROR),
        ("Stop", {"status": "normal"}, CodexStatus.IDLE),
        ("SessionEnd", {}, None),
    ],
)
def test_map_codex_event_covers_confirmed_events(
    event_name: str,
    payload: dict[str, object],
    expected: CodexStatus | None,
) -> None:
    """Codex hook events should map to the six product statuses."""
    assert HookEventMapper.map_codex_event(event_name, payload) is expected


@pytest.mark.parametrize(
    ("event_name", "payload", "expected"),
    [
        ("SessionStart", {}, CodexStatus.IDLE),
        ("UserPromptSubmit", {}, CodexStatus.WORKING),
        ("PreToolUse", {}, CodexStatus.WORKING),
        ("PostToolUse", {}, CodexStatus.WORKING),
        ("PreCompact", {}, CodexStatus.WORKING),
        ("SubagentStart", {}, CodexStatus.WORKING),
        ("PostToolUseFailure", {}, CodexStatus.ERROR),
        ("Stop", {"stop_reason": "error"}, CodexStatus.ERROR),
        ("Stop", {"stop_reason": "max_tokens"}, CodexStatus.ERROR),
        ("PermissionRequest", {}, CodexStatus.WAITING_APPROVAL),
        ("Notification", {}, CodexStatus.WAITING_USER_INPUT),
        ("SubagentStop", {}, CodexStatus.IDLE),
        ("Stop", {"stop_reason": "end_turn"}, CodexStatus.IDLE),
        ("SessionEnd", {}, None),
    ],
)
def test_map_claude_event_covers_confirmed_events(
    event_name: str,
    payload: dict[str, object],
    expected: CodexStatus | None,
) -> None:
    """Claude Code hook events should map to the six product statuses."""
    assert HookEventMapper.map_claude_event(event_name, payload) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"session_id": "session-a", "conversation_id": "conv", "thread_id": "thread"},
            "session-a",
        ),
        ({"conversation_id": "conv", "thread_id": "thread"}, "conv"),
        ({"thread_id": "thread"}, "thread"),
        ({"cwd": "D:/work/repo-name"}, "repo-name"),
        ({}, "global"),
    ],
)
def test_extract_session_key_uses_priority_chain(
    payload: dict[str, object],
    expected: str,
) -> None:
    """Session key extraction should prefer stable hook identifiers over cwd."""
    assert HookEventMapper._extract_session_key(payload) == expected


def test_unknown_or_bad_hook_events_return_none() -> None:
    """Bad hook input should be ignored instead of raising or inventing states."""
    assert HookEventMapper.map_codex_event("UnknownEvent", {}) is None
    assert HookEventMapper.map_claude_event("UnknownEvent", {}) is None
    assert HookEventMapper.map_codex_event("", {"status": object()}) is None


def test_hook_event_mapper_never_outputs_obsolete_ai_inferred_statuses() -> None:
    """Hook mapping should not revive the old eight-state speculation."""
    obsolete_names = {
        "DEEP_WORK",
        "NORMAL_WORK",
        "QUEUED",
        "REVIEW_READY",
        "AWAITING_APPROVAL",
    }
    outputs = [
        HookEventMapper.map_codex_event("SessionStart", {}),
        HookEventMapper.map_codex_event("PermissionRequest", {}),
        HookEventMapper.map_claude_event("Notification", {}),
        HookEventMapper.map_claude_event("Stop", {"stop_reason": "max_tokens"}),
    ]

    assert obsolete_names.isdisjoint(status.name for status in outputs if status is not None)
