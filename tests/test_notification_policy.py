"""Tests for pure notification transition policy."""

from __future__ import annotations

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.notification_policy import AlertKind, compute_alerts
from codex_traffic_lights.session_models import SessionStatus


def _session(
    status: CodexStatus,
    *,
    key: str = "vscode-ipc::thread-a",
    name: str = "repo-alpha",
) -> SessionStatus:
    return SessionStatus(
        session_key=key,
        thread_id=key.split("::", 1)[1],
        endpoint_id=key.split("::", 1)[0],
        display_name=name,
        status=status,
        last_updated=1_700_000_000.0,
    )


def test_compute_alerts_skips_initial_snapshot() -> None:
    """Startup snapshots should not replay historical alerts."""
    alerts = compute_alerts({}, [_session(CodexStatus.ERROR)], initialized=False)

    assert alerts == []


def test_compute_alerts_fires_waiting_approval_when_entering_approval() -> None:
    """Moving into approval waiting should create an approval alert."""
    alerts = compute_alerts(
        {"vscode-ipc::thread-a": CodexStatus.IDLE},
        [_session(CodexStatus.WAITING_APPROVAL)],
        initialized=True,
    )

    assert len(alerts) == 1
    assert alerts[0].kind is AlertKind.WAITING_APPROVAL
    assert alerts[0].old_status is CodexStatus.IDLE
    assert alerts[0].new_status is CodexStatus.WAITING_APPROVAL
    assert alerts[0].display_name == "repo-alpha"


def test_compute_alerts_dedupes_same_session_and_status() -> None:
    """Repeated updates in the same attention status should not notify again."""
    alerts = compute_alerts(
        {"vscode-ipc::thread-a": CodexStatus.WAITING_USER_INPUT},
        [_session(CodexStatus.WAITING_USER_INPUT)],
        initialized=True,
    )

    assert alerts == []


def test_compute_alerts_fires_distinct_attention_alert_kinds() -> None:
    """Entering user-input and error states should expose distinct alert kinds."""
    alerts = compute_alerts(
        {"vscode-ipc::thread-a": CodexStatus.WORKING},
        [
            _session(CodexStatus.WAITING_USER_INPUT),
            _session(
                CodexStatus.ERROR,
                key="vscode-ipc::thread-b",
                name="repo-beta",
            ),
        ],
        initialized=True,
    )

    assert [alert.kind for alert in alerts] == [
        AlertKind.WAITING_USER_INPUT,
        AlertKind.ERROR,
    ]


def test_compute_alerts_fires_completion_from_active_states() -> None:
    """Finishing work or waiting states should notify completion."""
    alerts = compute_alerts(
        {
            "vscode-ipc::thread-a": CodexStatus.WORKING,
            "vscode-ipc::thread-b": CodexStatus.WAITING_APPROVAL,
            "vscode-ipc::thread-c": CodexStatus.WAITING_USER_INPUT,
        },
        [
            _session(CodexStatus.IDLE),
            _session(CodexStatus.IDLE, key="vscode-ipc::thread-b", name="repo-beta"),
            _session(CodexStatus.IDLE, key="vscode-ipc::thread-c", name="repo-gamma"),
        ],
        initialized=True,
    )

    assert [alert.kind for alert in alerts] == [
        AlertKind.COMPLETED,
        AlertKind.COMPLETED,
        AlertKind.COMPLETED,
    ]


def test_compute_alerts_does_not_report_error_recovery_as_completion() -> None:
    """Recovering from error to idle should not be framed as task completion."""
    alerts = compute_alerts(
        {"vscode-ipc::thread-a": CodexStatus.ERROR},
        [_session(CodexStatus.IDLE)],
        initialized=True,
    )

    assert alerts == []


def test_compute_alerts_ignores_offline_and_working_entries() -> None:
    """Offline and working states should not trigger interruption alerts."""
    alerts = compute_alerts(
        {
            "vscode-ipc::thread-a": CodexStatus.IDLE,
            "vscode-ipc::thread-b": CodexStatus.IDLE,
        },
        [
            _session(CodexStatus.OFFLINE),
            _session(CodexStatus.WORKING, key="vscode-ipc::thread-b"),
        ],
        initialized=True,
    )

    assert alerts == []
