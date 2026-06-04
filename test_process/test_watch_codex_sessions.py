"""Parser tests for the live Codex session watcher."""

from __future__ import annotations

import json
from pathlib import Path

from watch_codex_sessions import load_sessions, summarize_sessions


def test_load_sessions_reads_two_distinct_real_shape_files(tmp_path: Path) -> None:
    """Two hook-shaped files should remain two distinct sessions."""
    _write_session(
        tmp_path / "one.json",
        session_key="codex::thread-a",
        display_name="repo-a",
        status="WORKING",
        updated_at=100.0,
    )
    _write_session(
        tmp_path / "two.json",
        session_key="codex::thread-b",
        display_name="repo-b",
        status="WAITING_APPROVAL",
        updated_at=101.0,
    )

    sessions = load_sessions(tmp_path)
    summary = summarize_sessions(sessions)

    assert summary["source"] == "hook-file"
    assert summary["source_count"] == 2
    assert summary["session_keys"] == ["codex::thread-a", "codex::thread-b"]
    assert summary["statuses"] == ["WORKING", "WAITING_APPROVAL"]


def test_load_sessions_ignores_invalid_or_unknown_status_files(tmp_path: Path) -> None:
    """Invalid files and unknown statuses should not become observed sessions."""
    (tmp_path / "bad-json.json").write_text("{bad", encoding="utf-8")
    _write_session(
        tmp_path / "unknown.json",
        session_key="codex::thread-c",
        display_name="repo-c",
        status="QUEUED",
        updated_at=102.0,
    )

    assert load_sessions(tmp_path) == []


def _write_session(
    path: Path,
    *,
    session_key: str,
    display_name: str,
    status: str,
    updated_at: float,
) -> None:
    path.write_text(
        json.dumps(
            {
                "session_key": session_key,
                "display_name": display_name,
                "status": status,
                "updated_at": updated_at,
            }
        ),
        encoding="utf-8",
    )
