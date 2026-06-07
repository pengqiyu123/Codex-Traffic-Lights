"""Tests for expanded-mode session matrix widgets."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.widgets.main_window import FramelessMainWindow
from codex_traffic_lights.widgets.session_column import COLUMN_HEIGHT
from codex_traffic_lights.widgets.session_matrix import MAX_VISIBLE_SESSIONS, SessionMatrixWidget


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure widget tests have a QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def make_session(index: int, status: CodexStatus = CodexStatus.IDLE) -> SessionStatus:
    """Create one deterministic session snapshot."""
    return SessionStatus(
        session_key=f"endpoint::{index}",
        thread_id=f"thread-{index}",
        endpoint_id="endpoint",
        display_name=f"repo-{index}",
        status=status,
        last_updated=1_700_000_000.0 + index,
    )


def test_session_matrix_shows_at_most_five_columns() -> None:
    """The matrix should cap visible session columns to five."""
    matrix = SessionMatrixWidget()

    matrix.set_sessions([make_session(index) for index in range(7)])

    assert len(matrix.session_columns) == MAX_VISIBLE_SESSIONS
    assert matrix.overflow_count == 2
    assert matrix.overflow_text == "+2"


def test_session_matrix_updates_existing_columns_by_session_key() -> None:
    """Existing column widgets should be reused when sessions refresh."""
    matrix = SessionMatrixWidget()
    sessions = [make_session(0, CodexStatus.IDLE), make_session(1, CodexStatus.WORKING)]
    matrix.set_sessions(sessions)
    first_column = matrix.session_columns[0]

    matrix.set_sessions([make_session(0, CodexStatus.ERROR)])

    assert matrix.session_columns == [first_column]
    assert first_column.session.status is CodexStatus.ERROR
    assert matrix.overflow_count == 0


def test_session_matrix_uses_compact_content_height() -> None:
    """Expanded matrix should not consume a large empty lower bay."""
    matrix = SessionMatrixWidget()

    matrix.set_sessions([make_session(0)])

    assert matrix.maximumHeight() <= COLUMN_HEIGHT + 20


def test_main_window_expanded_mode_uses_matrix_and_sessions() -> None:
    """Expanded main window should expose a compact multi-session panel."""
    window = FramelessMainWindow()
    sessions = [
        make_session(0, CodexStatus.WORKING),
        make_session(1, CodexStatus.WAITING_APPROVAL),
    ]

    window.set_sessions(sessions)
    window.toggle_expanded()

    assert window.is_expanded is True
    assert window._body.width() == 240
    assert window.width() == 272
    assert window.height() <= 340
    assert not window.session_matrix.isHidden()
    assert window.session_matrix.maximumHeight() <= COLUMN_HEIGHT + 20
    assert len(window.session_matrix.session_columns) == 2
    assert window.status_bar.status_text == "待审批确认 · 2 会话"


def test_main_window_expanded_toggle_fades_matrix_content() -> None:
    """Expanded content should fade in during the slide-open transition."""
    window = FramelessMainWindow()

    window.toggle_expanded()

    assert window._content_opacity_effect.opacity() == pytest.approx(0.0)
    assert window._content_fade_animation is not None
    assert window._content_fade_animation.endValue() == pytest.approx(1.0)


def test_main_window_escape_collapses_expanded_mode() -> None:
    """Pressing Escape should collapse expanded mode back to compact."""
    window = FramelessMainWindow()
    window.toggle_expanded()

    QTest.keyClick(window, Qt.Key_Escape)

    assert window.is_expanded is False
    assert window.width() == 104
    assert window.height() == 220
