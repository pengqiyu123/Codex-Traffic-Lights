"""Tests for expanded-mode session matrix widgets."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from codex_traffic_lights.models import CodexStatus
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.widgets.main_window import (
    EXPANDED_GLOBAL_HEIGHT,
    FramelessMainWindow,
)
from codex_traffic_lights.widgets.session_column import COLUMN_HEIGHT
from codex_traffic_lights.widgets.session_matrix import (
    MAX_VISIBLE_SESSIONS,
    RETIRE_DURATION_MS,
    SessionMatrixWidget,
)


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


def test_session_matrix_retires_removed_columns_before_deleting() -> None:
    """Removed sessions should show a short offline exit cue before disappearing."""
    matrix = SessionMatrixWidget()
    matrix.set_sessions([make_session(0, CodexStatus.IDLE)])
    first_column = matrix.session_columns[0]

    matrix.set_sessions([])

    assert matrix.session_columns == []
    assert matrix.display_columns == [first_column]
    assert first_column.is_retiring is True
    assert first_column.session.status is CodexStatus.OFFLINE
    assert "3 秒后隐藏" in first_column.toolTip()

    matrix.finish_retiring_session("endpoint::0")

    assert matrix.display_columns == []


def test_session_matrix_restores_session_that_reappears_during_retirement() -> None:
    """A session that reconnects during the exit cue should reuse and restore the column."""
    matrix = SessionMatrixWidget()
    matrix.set_sessions([make_session(0, CodexStatus.IDLE)])
    first_column = matrix.session_columns[0]
    matrix.set_sessions([])

    matrix.set_sessions([make_session(0, CodexStatus.WORKING)])

    assert matrix.session_columns == [first_column]
    assert matrix.display_columns == [first_column]
    assert first_column.is_retiring is False
    assert first_column.session.status is CodexStatus.WORKING


def test_session_matrix_cancels_retirement_when_session_reappears_in_overflow() -> None:
    """A reconnecting hidden session should stop showing the disconnected cue."""
    matrix = SessionMatrixWidget()
    matrix.set_sessions([make_session(0, CodexStatus.IDLE)])
    first_column = matrix.session_columns[0]
    matrix.set_sessions([])
    overflow_session = SessionStatus(
        session_key="endpoint::0",
        thread_id="thread-0",
        endpoint_id="endpoint",
        display_name="zzz-overflow",
        status=CodexStatus.WORKING,
        last_updated=1_700_000_000.0,
    )

    matrix.set_sessions(
        [
            overflow_session,
            *[make_session(index) for index in range(1, 6)],
        ]
    )

    assert first_column not in matrix.display_columns
    assert first_column.is_retiring is False
    assert first_column.session.status is CodexStatus.WORKING
    assert "endpoint::0" not in matrix._retire_timers
    assert matrix.overflow_count == 1


def test_session_matrix_does_not_retire_active_overflow_sessions() -> None:
    """Visible sessions that move behind overflow should not look disconnected."""
    matrix = SessionMatrixWidget()
    matrix.set_sessions([make_session(index) for index in range(5)])
    first_column = matrix.session_columns[0]
    overflow_session = SessionStatus(
        session_key="endpoint::0",
        thread_id="thread-0",
        endpoint_id="endpoint",
        display_name="zzz-overflow",
        status=CodexStatus.IDLE,
        last_updated=1_700_000_000.0,
    )

    sessions = [
        overflow_session,
        *[make_session(index) for index in range(1, 6)],
    ]
    matrix.set_sessions(sessions)

    assert first_column not in matrix.display_columns
    assert first_column.is_retiring is False
    assert matrix.overflow_count == 1


def test_session_matrix_retiring_timer_uses_three_second_duration() -> None:
    """Retiring columns should be scheduled for removal after three seconds."""
    matrix = SessionMatrixWidget()
    matrix.set_sessions([make_session(0, CodexStatus.IDLE)])

    matrix.set_sessions([])

    assert matrix._retire_timers["endpoint::0"].interval() == RETIRE_DURATION_MS


def test_session_matrix_uses_compact_content_height() -> None:
    """Expanded matrix should not consume a large empty lower bay."""
    matrix = SessionMatrixWidget()

    matrix.set_sessions([make_session(0)])

    assert matrix.maximumHeight() <= COLUMN_HEIGHT + 8


def test_session_matrix_uses_tight_card_padding_without_outer_frame() -> None:
    """The matrix should not draw a second container around project cards."""
    matrix = SessionMatrixWidget()

    margins = matrix.layout().contentsMargins()

    assert matrix.has_outer_frame is False
    assert margins.left() == 0
    assert margins.top() == 0
    assert margins.right() == 0
    assert margins.bottom() == 0


def test_session_matrix_scales_columns_spacing_and_overflow_marker() -> None:
    """Expanded zoom should scale matrix chrome without overflowing fixed width."""
    matrix = SessionMatrixWidget()
    matrix.resize(240, 80)
    matrix.set_sessions([make_session(index) for index in range(7)])
    default_height = matrix.maximumHeight()
    default_spacing = matrix.layout().spacing()
    default_marker_size = matrix._overflow_label.size()

    matrix.set_scale(2.0)

    assert matrix.maximumHeight() > default_height
    assert matrix.layout().spacing() > default_spacing
    assert matrix._overflow_label.width() > default_marker_size.width()
    matrix.resize(480, 160)
    matrix.set_scale(2.0)
    assert sum(column.width() for column in matrix.session_columns) <= matrix.width()


def test_session_matrix_uses_extra_width_for_fewer_session_names() -> None:
    """Sparse expanded sessions should use available panel width for longer names."""
    matrix = SessionMatrixWidget()
    matrix.resize(240, 80)

    matrix.set_sessions([make_session(0), make_session(1)])

    assert len(matrix.session_columns) == 2
    assert matrix.session_columns[0].width() >= 116
    assert matrix.session_columns[1].width() >= 116


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
    assert window.session_matrix.maximumHeight() <= COLUMN_HEIGHT + 8
    assert len(window.session_matrix.session_columns) == 2
    assert window.status_bar.status_text == "待审批确认 · 2 会话"


def test_main_window_expanded_restores_github_top_lamp_scale() -> None:
    """Expanded top lamps should preserve the stronger recent GitHub sizing."""
    window = FramelessMainWindow()

    window.toggle_expanded()

    assert EXPANDED_GLOBAL_HEIGHT == 88
    assert window._expanded_status_stack.height() == 88
    assert window.traffic_light.lamp_diameter == 30


def test_main_window_expanded_keeps_lamps_above_secondary_status_text() -> None:
    """Expanded top area should keep the lamps as the primary vertical focus."""
    window = FramelessMainWindow()

    window.toggle_expanded()

    assert not window._expanded_status_stack.isHidden()
    assert window.traffic_light.parent() is window._expanded_status_stack
    assert window.status_bar.parent() is window._expanded_status_stack
    assert window._expanded_status_layout.indexOf(window.traffic_light) < (
        window._expanded_status_layout.indexOf(window.status_bar)
    )


def test_main_window_expanded_scale_resizes_mini_lamps() -> None:
    """Window zoom should propagate into expanded mini session lamps."""
    window = FramelessMainWindow()
    window.set_sessions([make_session(0, CodexStatus.WORKING)])
    window.toggle_expanded()
    default_diameter = window.session_matrix.session_columns[0].mini_lamp_diameter

    window.set_window_scale(2.0)

    assert window.session_matrix.session_columns[0].mini_lamp_diameter > default_diameter


def test_main_window_offline_aggregate_with_retiring_matrix_column() -> None:
    """Retiring matrix columns should not keep the global status online."""
    window = FramelessMainWindow()
    window.set_sessions([make_session(0, CodexStatus.WORKING)])
    window.toggle_expanded()
    first_column = window.session_matrix.session_columns[0]

    window.set_sessions([])

    assert window.status_bar.status_text == CodexStatus.OFFLINE.label
    assert window.session_matrix.session_columns == []
    assert window.session_matrix.display_columns == [first_column]
    assert first_column.is_retiring is True


def test_main_window_expanded_status_text_uses_compact_height() -> None:
    """Expanded status text should not consume the top panel's spare height."""
    window = FramelessMainWindow()

    window.toggle_expanded()

    assert window.status_bar.maximumHeight() <= 28


def test_main_window_expanded_status_text_is_larger_and_bolder() -> None:
    """Expanded status text should be easier to read in the top panel."""
    window = FramelessMainWindow()
    default_font = window.status_bar._label.font()

    window.toggle_expanded()
    expanded_font = window.status_bar._label.font()

    assert expanded_font.pixelSize() == default_font.pixelSize() + 1
    assert expanded_font.weight() > default_font.weight()


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
