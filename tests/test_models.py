"""Tests for immutable model definitions."""

from dataclasses import FrozenInstanceError

import pytest

from codex_traffic_lights.models import AppConfig, CodexStatus, EdgeState, LightMode

EXPECTED_STATUS_NAMES = {
    "OFFLINE",
    "IDLE",
    "WORKING",
    "WAITING_APPROVAL",
    "WAITING_USER_INPUT",
    "ERROR",
}

OBSOLETE_STATUS_NAMES = {
    "DEEP_WORK",
    "NORMAL_WORK",
    "QUEUED",
    "REVIEW_READY",
    "AWAITING_APPROVAL",
}


def contains_chinese_text(value: str) -> bool:
    """Return True when a value contains at least one CJK character."""
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def test_codex_status_has_only_confirmed_six_members() -> None:
    """CodexStatus must follow the audited six-state product model."""
    assert {status.name for status in CodexStatus} == EXPECTED_STATUS_NAMES
    assert len(CodexStatus) == 6


def test_edge_state_tracks_free_snapped_and_docked_window_shapes() -> None:
    """EdgeState should model the floating window's three visible edge modes."""
    assert [state.value for state in EdgeState] == ["free", "snapped", "docked"]


def test_codex_status_excludes_obsolete_ai_inferred_members() -> None:
    """Deprecated eight-state guesses must not reappear in code."""
    actual_names = {status.name for status in CodexStatus}

    assert actual_names.isdisjoint(OBSOLETE_STATUS_NAMES)


def test_codex_status_labels_are_non_empty_chinese_text() -> None:
    """Every status needs a user-facing Chinese label."""
    for status in CodexStatus:
        assert status.label
        assert contains_chinese_text(status.label)


@pytest.mark.parametrize(
    ("status", "expected_red", "expected_yellow", "expected_green"),
    [
        (CodexStatus.OFFLINE, LightMode.SOLID, LightMode.OFF, LightMode.OFF),
        (CodexStatus.IDLE, LightMode.OFF, LightMode.OFF, LightMode.SOLID),
        (CodexStatus.WORKING, LightMode.OFF, LightMode.SLOW_BREATH, LightMode.OFF),
        (
            CodexStatus.WAITING_APPROVAL,
            LightMode.OFF,
            LightMode.SLOW_FLASH,
            LightMode.SLOW_FLASH,
        ),
        (
            CodexStatus.WAITING_USER_INPUT,
            LightMode.OFF,
            LightMode.INTERMITTENT_BLINK,
            LightMode.OFF,
        ),
        (CodexStatus.ERROR, LightMode.FAST_FLASH, LightMode.FAST_FLASH, LightMode.OFF),
    ],
)
def test_codex_status_light_state_matches_product_mapping(
    status: CodexStatus,
    expected_red: LightMode,
    expected_yellow: LightMode,
    expected_green: LightMode,
) -> None:
    """Each status carries the exact traffic-light mode from the PRD."""
    assert status.light_state.red is expected_red
    assert status.light_state.yellow is expected_yellow
    assert status.light_state.green is expected_green


def test_app_config_defaults_match_task_contract() -> None:
    """AppConfig defaults should make the app usable with no config file."""
    config = AppConfig()

    assert config.poll_interval_ms == 2000
    assert config.codex_process_name == "codex"
    assert config.app_server_url is None
    assert config.window_scale == 1.0
    assert config.notification_enabled is True
    assert config.sound_enabled is True
    assert config.sound_completed_path is None
    assert config.sound_waiting_approval_path is None
    assert config.sound_waiting_user_input_path is None
    assert config.sound_error_path is None
    assert config.vscode_ipc_enabled is True
    assert config.vscode_ipc_pipe_path == r"\\.\pipe\codex-ipc"
    assert config.vscode_ipc_reconnect_delay == 2.0
    assert config.vscode_ipc_read_timeout == 1.0


def test_app_config_is_frozen() -> None:
    """Runtime code should not mutate AppConfig in place."""
    config = AppConfig()

    with pytest.raises(FrozenInstanceError):
        config.poll_interval_ms = 1000  # type: ignore[misc]
