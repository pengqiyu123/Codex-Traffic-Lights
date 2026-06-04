"""Tests for the hook session file watcher."""

from __future__ import annotations

import json
import time
from pathlib import Path

from codex_traffic_lights.hook_bridge import HookFileWatcher
from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.session_models import SessionRegistry


def _write_session_file(
    sessions_dir: Path,
    *,
    file_name: str = "session.json",
    session_key: str = "endpoint::thread-a",
    status: CodexStatus = CodexStatus.WORKING,
    display_name: str = "repo-a",
    updated_at: float | None = None,
) -> None:
    """Write one hook session JSON file into a temp sessions directory."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_key": session_key,
        "status": status.name,
        "display_name": display_name,
        "updated_at": time.time() if updated_at is None else updated_at,
    }
    (sessions_dir / file_name).write_text(json.dumps(payload), encoding="utf-8")


def test_scan_sessions_dir_adds_new_session_to_registry(tmp_path: Path) -> None:
    """Scanning JSON files should update SessionRegistry with parsed snapshots."""
    registry = SessionRegistry()
    watcher = HookFileWatcher(AppConfig(), registry)
    watcher.sessions_dir = tmp_path
    _write_session_file(tmp_path)

    watcher._scan_sessions_dir()

    session = registry.get("endpoint::thread-a")
    assert session is not None
    assert session.endpoint_id == "endpoint"
    assert session.thread_id == "thread-a"
    assert session.display_name == "repo-a"
    assert session.status is CodexStatus.WORKING
    assert registry.count() == 1


def test_scan_sessions_dir_updates_existing_session_status(tmp_path: Path) -> None:
    """Changed hook files should replace previous session snapshots."""
    registry = SessionRegistry()
    watcher = HookFileWatcher(AppConfig(), registry)
    watcher.sessions_dir = tmp_path
    _write_session_file(tmp_path, status=CodexStatus.WORKING)
    watcher._scan_sessions_dir()

    _write_session_file(tmp_path, status=CodexStatus.WAITING_APPROVAL)
    watcher._scan_sessions_dir()

    session = registry.get("endpoint::thread-a")
    assert session is not None
    assert session.status is CodexStatus.WAITING_APPROVAL


def test_scan_sessions_dir_ignores_invalid_json(tmp_path: Path) -> None:
    """Broken hook output should not crash the watcher."""
    registry = SessionRegistry()
    watcher = HookFileWatcher(AppConfig(), registry)
    watcher.sessions_dir = tmp_path
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "bad.json").write_text("{bad json", encoding="utf-8")

    watcher._scan_sessions_dir()

    assert registry.count() == 0


def test_cleanup_stale_removes_sessions_older_than_five_minutes(tmp_path: Path) -> None:
    """Sessions without updates for five minutes should be removed."""
    registry = SessionRegistry()
    watcher = HookFileWatcher(AppConfig(), registry)
    watcher.sessions_dir = tmp_path
    stale_updated_at = time.time() - HookFileWatcher.STALE_AFTER_SECONDS - 1
    _write_session_file(tmp_path, updated_at=stale_updated_at)
    watcher._scan_sessions_dir()

    watcher._cleanup_stale()

    assert registry.count() == 0
    assert not (tmp_path / "session.json").exists()


def test_status_changed_emits_only_when_aggregate_status_changes(tmp_path: Path) -> None:
    """Watcher status signal should emit only on aggregate status transitions."""
    registry = SessionRegistry()
    watcher = HookFileWatcher(AppConfig(), registry)
    watcher.sessions_dir = tmp_path
    emitted: list[CodexStatus] = []
    watcher.status_changed.connect(emitted.append)

    _write_session_file(tmp_path, status=CodexStatus.WORKING)
    watcher._scan_sessions_dir()
    watcher._scan_sessions_dir()
    _write_session_file(tmp_path, status=CodexStatus.ERROR)
    watcher._scan_sessions_dir()

    assert emitted == [CodexStatus.WORKING, CodexStatus.ERROR]
