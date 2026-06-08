"""Tests for notification and sound alert orchestration."""

from __future__ import annotations

from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.notification_controller import NotificationController
from codex_traffic_lights.notification_policy import AlertKind
from codex_traffic_lights.session_models import SessionStatus


class FakeTray:
    """Record tray notification messages."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def show_message(self, title: str, text: str) -> None:
        self.messages.append((title, text))


class FakeSoundPlayer:
    """Record requested alert sounds."""

    def __init__(self) -> None:
        self.played: list[AlertKind] = []

    def play(self, kind: AlertKind) -> None:
        self.played.append(kind)


def _session(
    status: CodexStatus,
    *,
    key: str = "vscode-ipc::thread-a",
    name: str = "repo-alpha",
    endpoint_id: str = "vscode-ipc",
) -> SessionStatus:
    return SessionStatus(
        session_key=key,
        thread_id=key.split("::", 1)[-1],
        endpoint_id=endpoint_id,
        display_name=name,
        status=status,
        last_updated=1_700_000_000.0,
    )


def test_notification_controller_skips_startup_snapshot() -> None:
    """Existing attention states at startup should not notify."""
    tray = FakeTray()
    sound = FakeSoundPlayer()
    controller = NotificationController(tray, sound)

    controller.set_sessions([_session(CodexStatus.ERROR)])

    assert tray.messages == []
    assert sound.played == []


def test_notification_controller_reports_completion_sound_without_tray_message() -> None:
    """Notification popups are hidden while completion sounds remain active."""
    tray = FakeTray()
    sound = FakeSoundPlayer()
    controller = NotificationController(tray, sound)
    controller.set_sessions([_session(CodexStatus.WORKING)])

    controller.set_sessions([_session(CodexStatus.IDLE)])

    assert tray.messages == []
    assert sound.played == [AlertKind.COMPLETED]


def test_notification_controller_keeps_tray_messages_hidden_for_alerts() -> None:
    """Alert events should not show tray popups while notification UI is hidden."""
    tray = FakeTray()
    sound = FakeSoundPlayer()
    controller = NotificationController(tray, sound)
    controller.set_sessions([_session(CodexStatus.IDLE)])

    controller.set_sessions([_session(CodexStatus.WAITING_APPROVAL)])
    controller.set_sessions([_session(CodexStatus.WORKING)])
    controller.set_sessions([_session(CodexStatus.WAITING_USER_INPUT)])
    controller.set_sessions([_session(CodexStatus.WORKING)])
    controller.set_sessions([_session(CodexStatus.ERROR)])

    assert tray.messages == []
    assert sound.played == [
        AlertKind.WAITING_APPROVAL,
        AlertKind.WAITING_USER_INPUT,
        AlertKind.ERROR,
    ]


def test_notification_controller_respects_sound_switch_only() -> None:
    """Hidden notification popups should stay off; sound switch still gates audio."""
    tray = FakeTray()
    sound = FakeSoundPlayer()
    controller = NotificationController(tray, sound)
    controller.set_config(AppConfig(notification_enabled=False, sound_enabled=True))
    controller.set_sessions([_session(CodexStatus.IDLE)])

    controller.set_sessions([_session(CodexStatus.ERROR)])

    assert tray.messages == []
    assert sound.played == [AlertKind.ERROR]

    controller.set_config(AppConfig(notification_enabled=True, sound_enabled=False))
    controller.set_sessions([_session(CodexStatus.IDLE)])
    controller.set_sessions([_session(CodexStatus.WAITING_APPROVAL)])

    assert tray.messages == []
    assert sound.played == [AlertKind.ERROR]


def test_notification_controller_filters_non_codex_sessions() -> None:
    """Claude sessions should not trigger Codex product alerts."""
    tray = FakeTray()
    sound = FakeSoundPlayer()
    controller = NotificationController(tray, sound)
    controller.set_sessions([_session(CodexStatus.IDLE)])

    controller.set_sessions(
        [
            _session(CodexStatus.IDLE),
            _session(
                CodexStatus.ERROR,
                key="claude::thread-a",
                name="claude",
                endpoint_id="claude",
            ),
        ]
    )

    assert tray.messages == []
    assert sound.played == []
