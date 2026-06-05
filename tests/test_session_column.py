"""Tests for expanded-mode session column widgets."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.widgets.session_column import SessionColumnWidget
from codex_traffic_lights.widgets.traffic_light import STATUS_COLORS


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure widget tests have a QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_session(
    status: CodexStatus = CodexStatus.WORKING,
    *,
    key: str = "endpoint::thread-a",
    name: str = "repo-alpha",
) -> SessionStatus:
    """Create a deterministic session snapshot for UI tests."""
    return SessionStatus(
        session_key=key,
        thread_id=key.split("::", 1)[1],
        endpoint_id=key.split("::", 1)[0],
        display_name=name,
        status=status,
        last_updated=1_700_000_000.0,
    )


def test_session_column_locks_pixel_size_and_status() -> None:
    """Session columns should keep the 44px matrix column contract."""
    session = make_session(CodexStatus.WAITING_APPROVAL)
    column = SessionColumnWidget(session)

    assert column.minimumSize() == QSize(44, 68)
    assert column.maximumWidth() == 44
    assert column.session is session
    assert column.status_color == STATUS_COLORS[CodexStatus.WAITING_APPROVAL]


def test_session_column_updates_session_tooltip_and_color() -> None:
    """Updating a session should refresh status color and tooltip details."""
    column = SessionColumnWidget(make_session(CodexStatus.IDLE, name="old"))
    updated = make_session(CodexStatus.ERROR, key="vscode::thread-b", name="repo-beta")

    column.set_session(updated)

    assert column.session is updated
    assert column.status_color == STATUS_COLORS[CodexStatus.ERROR]
    assert "repo-beta" in column.toolTip()
    assert "thread-b" in column.toolTip()
    assert CodexStatus.ERROR.label in column.toolTip()


def test_session_column_renders_without_error() -> None:
    """Session column painting should render into a pixmap without crashing."""
    column = SessionColumnWidget(make_session(CodexStatus.WAITING_USER_INPUT))
    column.resize(44, 68)
    pixmap = QPixmap(column.size())

    column.render(pixmap)

    assert pixmap.size() == QSize(44, 68)
