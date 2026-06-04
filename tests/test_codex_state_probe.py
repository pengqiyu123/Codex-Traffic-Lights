"""Tests for the read-only Codex state probe."""

from __future__ import annotations

from pathlib import Path

from codex_traffic_lights.codex_state_probe import (
    build_non_idle_simulations,
    build_product_state_candidates,
    collect_schema_evidence,
    dedupe_paths,
    extract_string_union_values,
    extract_thread_status_types,
)


def test_extract_thread_status_types_from_generated_ts_shape() -> None:
    """ThreadStatus object variants should be extracted from generated TypeScript."""
    source = '''
export type ThreadStatus =
  | { "type": "notLoaded" }
  | { "type": "idle" }
  | { "type": "systemError" }
  | { "type": "active", activeFlags: Array<ThreadActiveFlag>, };
'''

    assert extract_thread_status_types(source) == ["notLoaded", "idle", "systemError", "active"]


def test_extract_string_union_values_from_generated_ts_shape() -> None:
    """String literal unions should be extracted without treating comments as values."""
    source = '''
// GENERATED CODE! DO NOT MODIFY BY HAND!
export type TurnStatus = "completed" | "interrupted" | "failed" | "inProgress";
'''

    assert extract_string_union_values(source, "TurnStatus") == [
        "completed",
        "interrupted",
        "failed",
        "inProgress",
    ]


def test_collect_schema_evidence_from_generated_file_set(tmp_path: Path) -> None:
    """The probe should collect the three status axes relevant to traffic-light mapping."""
    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "ThreadStatus.ts").write_text(
        'export type ThreadStatus = { "type": "notLoaded" } | { "type": "active", '
        "activeFlags: Array<ThreadActiveFlag>, };",
        encoding="utf-8",
    )
    (v2 / "ThreadActiveFlag.ts").write_text(
        'export type ThreadActiveFlag = "waitingOnApproval" | "waitingOnUserInput";',
        encoding="utf-8",
    )
    (v2 / "TurnStatus.ts").write_text(
        'export type TurnStatus = "completed" | "interrupted" | "failed" | "inProgress";',
        encoding="utf-8",
    )

    evidence = collect_schema_evidence(tmp_path)

    assert evidence.thread_status_types == ("notLoaded", "active")
    assert evidence.thread_active_flags == ("waitingOnApproval", "waitingOnUserInput")
    assert evidence.turn_statuses == ("completed", "interrupted", "failed", "inProgress")


def test_product_state_candidates_are_seven_without_obsolete_guesses() -> None:
    """Evidence-based candidates should not revive the old inferred eight-state model."""
    candidates = build_product_state_candidates()
    names = [candidate.name for candidate in candidates]

    assert names == [
        "OFFLINE",
        "NOT_LOADED",
        "IDLE",
        "WORKING",
        "WAITING_APPROVAL",
        "WAITING_USER_INPUT",
        "ERROR",
    ]
    assert set(names).isdisjoint({"DEEP_WORK", "NORMAL_WORK", "QUEUED", "REVIEW_READY"})


def test_non_idle_simulations_cover_six_candidate_states() -> None:
    """Six non-idle simulations should be available for manual and diagnostic replay."""
    simulations = build_non_idle_simulations()

    assert [simulation["candidate_product_status"] for simulation in simulations] == [
        "OFFLINE",
        "NOT_LOADED",
        "WORKING",
        "WAITING_APPROVAL",
        "WAITING_USER_INPUT",
        "ERROR",
    ]


def test_dedupe_paths_preserves_order_case_insensitively_on_windows() -> None:
    """Entrypoint discovery should not probe the same Windows path twice."""
    paths = [
        r"C:\Users\pengq\AppData\Roaming\npm\codex.cmd",
        r"c:\users\pengq\appdata\roaming\npm\CODEX.cmd",
        r"C:\Users\pengq\.vscode\extensions\openai.chatgpt\codex.exe",
    ]

    assert dedupe_paths(paths) == [
        r"C:\Users\pengq\AppData\Roaming\npm\codex.cmd",
        r"C:\Users\pengq\.vscode\extensions\openai.chatgpt\codex.exe",
    ]
