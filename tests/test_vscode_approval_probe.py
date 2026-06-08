"""Tests for the redacted VSCode Codex approval probe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "test_process" / "vscode_codex_approval_probe.mjs"


def run_probe_summary(message: dict[str, object]) -> dict[str, object]:
    """Ask the Node probe module to summarize one IPC message."""
    script = f"""
import {{ summarizeMessage }} from {json.dumps(PROBE.as_uri())};
const message = {json.dumps(message)};
console.log(JSON.stringify(summarizeMessage(message)));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def test_probe_summarizes_plan_confirmation_snapshot_without_sensitive_text() -> None:
    """Snapshot summaries should expose only safe plan confirmation status fields."""
    message: dict[str, object] = {
        "type": "broadcast",
        "method": "thread-stream-state-changed",
        "params": {
            "conversationId": "conversation-123456",
            "hostId": "local",
            "change": {
                "type": "snapshot",
                "revision": 12,
                "conversationState": {
                    "id": "conversation-123456",
                    "threadGoalResumeConfirmation": {
                        "status": "waiting_for_confirmation",
                        "plan": "secret plan body",
                        "cwd": "D:/secret/project",
                    },
                    "threadRuntimeStatus": {"type": "idle"},
                    "turns": [{"status": "completed"}],
                },
            },
        },
    }

    summary = run_probe_summary(message)
    dumped = json.dumps(summary)

    confirmation = summary["change"]["conversationState"]["threadGoalResumeConfirmation"]
    assert confirmation == {
        "kind": "object",
        "keys": ["cwd", "plan", "status"],
        "status": "waiting_for_confirmation",
    }
    assert "secret plan body" not in dumped
    assert "D:/secret/project" not in dumped


def test_probe_summarizes_plan_confirmation_patch_without_sensitive_text() -> None:
    """Patch summaries should include confirmation paths and redacted values."""
    message: dict[str, object] = {
        "type": "broadcast",
        "method": "thread-stream-state-changed",
        "params": {
            "conversationId": "conversation-123456",
            "change": {
                "type": "patches",
                "revision": 13,
                "patches": [
                    {
                        "op": "replace",
                        "path": ["threadGoalResumeConfirmation", "status"],
                        "value": "pending",
                    },
                    {
                        "op": "replace",
                        "path": ["threadGoalResumeConfirmation", "plan"],
                        "value": "secret plan body",
                    },
                ],
            },
        },
    }

    summary = run_probe_summary(message)
    dumped = json.dumps(summary)

    patches = summary["change"]["patches"]
    assert patches[0] == {
        "op": "replace",
        "path": "/threadGoalResumeConfirmation/status",
        "value": "pending",
    }
    assert patches[1] == {
        "op": "replace",
        "path": "/threadGoalResumeConfirmation/plan",
        "value": {"kind": "string", "length": 16},
    }
    assert "secret plan body" not in dumped


def test_probe_summarizes_pending_plan_implementation_without_plan_text() -> None:
    """Plan implementation summaries should expose only completion state."""
    message: dict[str, object] = {
        "type": "broadcast",
        "method": "thread-stream-state-changed",
        "params": {
            "conversationId": "conversation-123456",
            "change": {
                "type": "snapshot",
                "revision": 14,
                "conversationState": {
                    "turns": [
                        {
                            "status": "completed",
                            "items": [
                                {
                                    "type": "planImplementation",
                                    "isCompleted": False,
                                    "planContent": "secret implementation plan",
                                    "cwd": "D:/secret/project",
                                }
                            ],
                        }
                    ],
                },
            },
        },
    }

    summary = run_probe_summary(message)
    dumped = json.dumps(summary)

    item = summary["change"]["conversationState"]["recentTurns"][0]["itemTypes"][0]
    assert item == {
        "index": 0,
        "keys": ["cwd", "isCompleted", "planContent", "type"],
        "type": "planImplementation",
        "isCompleted": False,
    }
    assert "secret implementation plan" not in dumped
    assert "D:/secret/project" not in dumped


def test_probe_summarizes_completed_plan_implementation() -> None:
    """Completed plan implementation items should expose their safe boolean state."""
    message: dict[str, object] = {
        "type": "broadcast",
        "method": "thread-stream-state-changed",
        "params": {
            "conversationId": "conversation-123456",
            "change": {
                "type": "snapshot",
                "revision": 15,
                "conversationState": {
                    "turns": [
                        {
                            "status": "completed",
                            "items": [
                                {
                                    "type": "planImplementation",
                                    "isCompleted": True,
                                    "planContent": "secret implementation plan",
                                }
                            ],
                        }
                    ],
                },
            },
        },
    }

    summary = run_probe_summary(message)
    dumped = json.dumps(summary)

    item = summary["change"]["conversationState"]["recentTurns"][0]["itemTypes"][0]
    assert item == {
        "index": 0,
        "keys": ["isCompleted", "planContent", "type"],
        "type": "planImplementation",
        "isCompleted": True,
    }
    assert "secret implementation plan" not in dumped


def test_probe_summarizes_plan_implementation_completion_patch() -> None:
    """Completion patches should expose boolean state while redacting plan content."""
    message: dict[str, object] = {
        "type": "broadcast",
        "method": "thread-stream-state-changed",
        "params": {
            "conversationId": "conversation-123456",
            "change": {
                "type": "patches",
                "revision": 16,
                "patches": [
                    {
                        "op": "replace",
                        "path": ["turns", 0, "items", 0, "isCompleted"],
                        "value": False,
                    },
                    {
                        "op": "replace",
                        "path": ["turns", 0, "items", 0, "planContent"],
                        "value": "secret implementation plan",
                    },
                ],
            },
        },
    }

    summary = run_probe_summary(message)
    dumped = json.dumps(summary)

    patches = summary["change"]["patches"]
    assert patches[0] == {
        "op": "replace",
        "path": "/turns/0/items/0/isCompleted",
        "value": False,
    }
    assert patches[1] == {
        "op": "replace",
        "path": "/turns/0/items/0/planContent",
        "value": {"kind": "string", "length": 26},
    }
    assert "secret implementation plan" not in dumped
