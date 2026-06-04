"""Tests for the Codex app-server connector."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.app_server_connector import AppServerConnector
from codex_traffic_lights.models import AppConfig, CodexStatus
from codex_traffic_lights.session_models import SessionRegistry, SessionStatus


class FakeAppServerClient:
    """Small app-server transport fake for connector tests."""

    def __init__(
        self,
        *,
        connected: bool = True,
        raises_on_connect: bool = False,
        loaded_pages: list[dict[str, object]] | None = None,
        threads: dict[str, dict[str, object]] | None = None,
        notifications: list[dict[str, object]] | None = None,
    ) -> None:
        """Create a fake transport with deterministic responses."""
        self.connected = connected
        self.raises_on_connect = raises_on_connect
        self.loaded_pages = loaded_pages or [{"data": [], "nextCursor": None}]
        self.threads = threads or {}
        self.notifications = notifications or []
        self.calls: list[tuple[str, Mapping[str, object]]] = []
        self.closed = False

    def connect(self) -> bool:
        """Return configured connection state."""
        if self.raises_on_connect:
            raise OSError("connection refused")
        return self.connected

    def call(self, method: str, params: Mapping[str, object]) -> Mapping[str, object] | None:
        """Return fake JSON-RPC responses for selected methods."""
        self.calls.append((method, dict(params)))
        if method == "thread/loaded/list":
            return self.loaded_pages.pop(0)
        if method == "thread/read":
            thread_id = params["threadId"]
            return {"thread": self.threads[str(thread_id)]}
        return {}

    def iter_notifications(self) -> Iterator[Mapping[str, object]]:
        """Yield preloaded notifications."""
        yield from self.notifications

    def close(self) -> None:
        """Mark the fake client closed."""
        self.closed = True


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure PyQt signals have an application object during tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _thread_payload(
    thread_id: str,
    *,
    status: Mapping[str, object] | None = None,
    cwd: str = "D:/work/repo-a",
    name: str | None = None,
) -> dict[str, object]:
    """Build the subset of Thread payload fields used by the connector."""
    return {
        "id": thread_id,
        "cwd": cwd,
        "name": name,
        "preview": "first prompt",
        "status": dict(status or {"type": "idle"}),
    }


def test_handle_notification_updates_registry_and_emits_session_status() -> None:
    """thread/status/changed should update one session and emit aggregate status."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    session_spy = QSignalSpy(connector.session_updated)
    status_spy = QSignalSpy(connector.status_changed)

    connector._handle_notification(
        "thread/status/changed",
        {
            "endpointId": "vscode-main",
            "threadId": "thread-a",
            "status": {"type": "active", "activeFlags": ["waitingOnApproval"]},
        },
    )

    session = registry.get("vscode-main::thread-a")
    assert session is not None
    assert session.status is CodexStatus.WAITING_APPROVAL
    assert session.display_name == "thread-a"
    assert len(session_spy) == 1
    assert isinstance(session_spy[0][0], SessionStatus)
    assert status_spy[0][0] is CodexStatus.WAITING_APPROVAL


def test_subscribe_threads_reads_loaded_thread_list_and_updates_registry() -> None:
    """Loaded thread discovery should read each thread and seed session state."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    fake_client = FakeAppServerClient(
        loaded_pages=[{"data": ["thread-a", "thread-b"], "nextCursor": None}],
        threads={
            "thread-a": _thread_payload(
                "thread-a",
                status={"type": "active", "activeFlags": []},
                cwd="D:/work/repo-a",
            ),
            "thread-b": _thread_payload(
                "thread-b",
                status={"type": "idle"},
                cwd="D:/work/repo-b",
            ),
        },
    )
    connector._client = fake_client
    session_spy = QSignalSpy(connector.session_updated)

    connector._subscribe_threads()

    assert [method for method, _params in fake_client.calls] == [
        "thread/loaded/list",
        "thread/read",
        "thread/read",
    ]
    assert registry.get("ws://127.0.0.1:18731::thread-a").status is CodexStatus.WORKING  # type: ignore[union-attr]
    assert registry.get("ws://127.0.0.1:18731::thread-b").status is CodexStatus.IDLE  # type: ignore[union-attr]
    assert len(session_spy) == 2


def test_session_updated_signal_emits_session_status_object() -> None:
    """Session updates should emit the concrete SessionStatus payload."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    session_spy = QSignalSpy(connector.session_updated)

    connector._handle_thread_started(
        {
            "thread": _thread_payload(
                "thread-a",
                status={"type": "active", "activeFlags": ["waitingOnUserInput"]},
                name="Repo A",
            )
        }
    )

    emitted = session_spy[0][0]
    assert isinstance(emitted, SessionStatus)
    assert emitted.display_name == "Repo A"
    assert emitted.status is CodexStatus.WAITING_USER_INPUT


def test_connect_failure_is_graceful_and_does_not_emit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connection failure should not crash or emit stale statuses."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    fake_client = FakeAppServerClient(connected=False)
    monkeypatch.setattr(connector, "_build_client", lambda: fake_client)
    status_spy = QSignalSpy(connector.status_changed)

    assert connector._connect() is False

    assert fake_client.closed is True
    assert registry.count() == 0
    assert len(status_spy) == 0


def test_connect_failure_from_exception_is_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport exceptions during connect should be swallowed as a failed connection."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    fake_client = FakeAppServerClient(raises_on_connect=True)
    monkeypatch.setattr(connector, "_build_client", lambda: fake_client)

    assert connector._connect() is False
    assert fake_client.closed is True


def test_thread_started_and_closed_update_registry_and_aggregate_status() -> None:
    """Thread lifecycle notifications should add and remove registry sessions."""
    registry = SessionRegistry()
    connector = AppServerConnector(AppConfig(app_server_url="ws://127.0.0.1:18731"), registry)
    status_spy = QSignalSpy(connector.status_changed)

    connector._handle_thread_started(
        {
            "thread": _thread_payload(
                "thread-a",
                status={"type": "active", "activeFlags": []},
                cwd="D:/work/repo-a",
            )
        }
    )
    connector._handle_thread_closed({"threadId": "thread-a"})

    assert registry.count() == 0
    assert [arguments[0] for arguments in status_spy] == [
        CodexStatus.WORKING,
        CodexStatus.OFFLINE,
    ]


def test_connector_uses_five_second_retry_interval() -> None:
    """Failed connections should retry every five seconds in the run loop."""
    assert AppServerConnector.RETRY_INTERVAL_MS == 5000
