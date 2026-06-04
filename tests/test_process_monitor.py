"""Tests for process monitoring and fallback status detection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.process_monitor import ProcessMonitor


@dataclass
class FakeProcess:
    """Small psutil.Process stand-in for monitor tests."""

    process_name: str
    command_line: list[str]
    pid: int = 1234

    def name(self) -> str:
        """Return the fake process name."""
        return self.process_name

    def cmdline(self) -> list[str]:
        """Return the fake command line."""
        return self.command_line


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure PyQt signals have an application object during tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_monitor() -> ProcessMonitor:
    """Create a monitor with deterministic test configuration."""
    return ProcessMonitor(AppConfig(codex_process_name="codex"))


def patch_processes(
    monkeypatch: pytest.MonkeyPatch,
    processes: Iterable[FakeProcess],
) -> None:
    """Patch psutil.process_iter with a fixed process list."""
    monkeypatch.setattr(
        "codex_traffic_lights.process_monitor.psutil.process_iter",
        lambda: iter(processes),
    )


def test_fallback_status_is_offline_when_no_codex_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No matching Codex process should map to OFFLINE."""
    monitor = make_monitor()
    patch_processes(monkeypatch, [])

    assert monitor._detect_fallback_status() is CodexStatus.OFFLINE


def test_fallback_status_is_working_when_name_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process name containing the configured name should map to IDLE only."""
    monitor = make_monitor()
    patch_processes(monkeypatch, [FakeProcess("codex.exe", [])])

    assert monitor._detect_fallback_status() is CodexStatus.IDLE


def test_fallback_status_is_working_when_cmdline_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A command-line argument containing the configured name should map to IDLE only."""
    monitor = make_monitor()
    patch_processes(monkeypatch, [FakeProcess("python.exe", ["python", "-m", "codex"])])

    assert monitor._detect_fallback_status() is CodexStatus.IDLE


def test_fallback_status_is_idle_for_vscode_app_server_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VSCode Codex app-server presence alone should not mean Codex is working."""
    monitor = make_monitor()
    patch_processes(
        monkeypatch,
        [
            FakeProcess(
                "codex.exe",
                [
                    "codex.exe",
                    "app-server",
                    "--analytics-default-enabled",
                ],
            )
        ],
    )

    assert monitor._detect_fallback_status() is CodexStatus.IDLE


def test_fallback_status_ignores_own_traffic_lights_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The monitor app itself should not be mistaken for Codex CLI."""
    monitor = make_monitor()
    patch_processes(
        monkeypatch,
        [FakeProcess("codex-traffic-lights.exe", ["codex_traffic_lights"])],
    )

    assert monitor._detect_fallback_status() is CodexStatus.OFFLINE


def test_fallback_status_is_error_when_previous_online_now_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A previously active Codex process disappearing should map to ERROR."""
    monitor = make_monitor()
    monitor._previous_status = CodexStatus.WORKING
    patch_processes(monkeypatch, [])

    assert monitor._detect_fallback_status() is CodexStatus.ERROR


@pytest.mark.parametrize(
    ("event", "expected_status"),
    [
        (
            {"status": {"type": "active", "activeFlags": ["waitingOnApproval"]}},
            CodexStatus.WAITING_APPROVAL,
        ),
        (
            {"status": {"type": "active", "activeFlags": ["waitingOnUserInput"]}},
            CodexStatus.WAITING_USER_INPUT,
        ),
        ({"status": {"type": "idle"}}, CodexStatus.IDLE),
        ({"status": {"type": "systemError"}}, CodexStatus.ERROR),
    ],
)
def test_apply_app_server_event_emits_mapped_status(
    event: dict[str, object],
    expected_status: CodexStatus,
) -> None:
    """App-server events should emit mapped six-state product statuses."""
    monitor = make_monitor()
    spy = QSignalSpy(monitor.status_changed)

    monitor.apply_app_server_event(event)

    assert len(spy) == 1
    assert spy[0][0] is expected_status


def test_status_changed_emits_only_when_status_changes() -> None:
    """Repeated status values should not emit duplicate status_changed signals."""
    monitor = make_monitor()
    spy = QSignalSpy(monitor.status_changed)

    monitor.apply_app_server_event({"status": {"type": "idle"}})
    monitor.apply_app_server_event({"status": {"type": "idle"}})
    monitor.apply_app_server_event({"status": "inProgress"})

    assert [arguments[0] for arguments in spy] == [
        CodexStatus.IDLE,
        CodexStatus.WORKING,
    ]


def test_apply_app_server_event_updates_registry_and_aggregates_status() -> None:
    """Thread-scoped app-server events should update registry and emit aggregate status."""
    monitor = make_monitor()
    spy = QSignalSpy(monitor.status_changed)
    sessions_spy = QSignalSpy(monitor.sessions_changed)

    monitor.apply_app_server_event(
        {
            "endpointId": "vscode-main",
            "threadId": "thread-a",
            "cwd": "D:/work/repo-a",
            "status": {"type": "active", "activeFlags": []},
        }
    )
    monitor.apply_app_server_event(
        {
            "endpointId": "vscode-main",
            "threadId": "thread-b",
            "cwd": "D:/work/repo-b",
            "status": {"type": "systemError"},
        }
    )

    first_session = monitor.registry.get("vscode-main::thread-a")
    second_session = monitor.registry.get("vscode-main::thread-b")

    assert first_session is not None
    assert first_session.display_name == "repo-a"
    assert first_session.status is CodexStatus.WORKING
    assert second_session is not None
    assert second_session.display_name == "repo-b"
    assert second_session.status is CodexStatus.ERROR
    assert [len(arguments[0]) for arguments in sessions_spy] == [1, 2]
    assert [arguments[0] for arguments in spy] == [
        CodexStatus.WORKING,
        CodexStatus.ERROR,
    ]
