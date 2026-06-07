"""Expanded-mode multi-session mini traffic-light matrix."""

from __future__ import annotations

from typing import cast

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.widgets.session_column import (
    COLUMN_HEIGHT,
    COLUMN_WIDTH,
    MAX_COLUMN_WIDTH,
    MIN_COLUMN_WIDTH,
    SessionColumnWidget,
)
from codex_traffic_lights.widgets.traffic_light import BORDER_COLOR, PANEL_COLOR

MAX_VISIBLE_SESSIONS = 5
COLUMN_SPACING = 6
MATRIX_VERTICAL_PADDING = 16
BASE_MARGIN = 8
BASE_OVERFLOW_WIDTH = 28
BASE_OVERFLOW_HEIGHT = 18
BASE_OVERFLOW_FONT_SIZE = 9
MIN_SCALE = 0.5
MAX_SCALE = 2.0


class SessionMatrixWidget(QWidget):
    """Show up to five Codex sessions as adjacent mini traffic-light columns."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create an empty session matrix."""
        super().__init__(parent)
        self._columns_by_key: dict[str, SessionColumnWidget] = {}
        self._session_columns: list[SessionColumnWidget] = []
        self._overflow_count = 0
        self._scale = 1.0
        self._overflow_label = QLabel("", self)
        self._overflow_label.setObjectName("session_overflow_label")
        self._overflow_label.setAlignment(Qt.AlignCenter)
        self._overflow_label.setFixedSize(BASE_OVERFLOW_WIDTH, BASE_OVERFLOW_HEIGHT)
        self._overflow_label.setFont(QFont("Consolas", BASE_OVERFLOW_FONT_SIZE, QFont.Bold))
        self._overflow_label.setStyleSheet(
            "color: #6A6A70; background: transparent; border: 1px solid #2A2A30; "
            "border-radius: 8px;"
        )
        self._overflow_label.hide()

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(COLUMN_SPACING)
        self._layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self._apply_scaled_geometry()

    @property
    def session_columns(self) -> list[SessionColumnWidget]:
        """Return visible session columns in display order."""
        return list(self._session_columns)

    @property
    def overflow_count(self) -> int:
        """Return the count of sessions hidden behind the overflow marker."""
        return self._overflow_count

    @property
    def overflow_text(self) -> str:
        """Return the visible overflow label text."""
        return self._overflow_label.text()

    def set_scale(self, scale: float) -> None:
        """Scale matrix spacing, visible columns, and overflow marker."""
        self._scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self._apply_scaled_geometry()
        for column in self._columns_by_key.values():
            column.set_scale(self._scale)
        self._apply_adaptive_column_widths()
        self._position_overflow_label()
        self.update()

    def set_sessions(self, sessions: list[SessionStatus]) -> None:
        """Create, update, and remove visible session columns."""
        ordered_sessions = sorted(
            sessions,
            key=lambda session: (
                session.display_name.casefold(),
                session.endpoint_id.casefold(),
                session.thread_id.casefold(),
            ),
        )
        visible_sessions = ordered_sessions[:MAX_VISIBLE_SESSIONS]
        visible_keys = {session.session_key for session in visible_sessions}

        for session_key, column in list(self._columns_by_key.items()):
            if session_key not in visible_keys:
                self._layout.removeWidget(column)
                column.setParent(cast(QWidget, None))
                column.deleteLater()
                del self._columns_by_key[session_key]

        self._session_columns = []
        for index, session in enumerate(visible_sessions):
            maybe_column = self._columns_by_key.get(session.session_key)
            if maybe_column is None:
                column = SessionColumnWidget(session)
                column.set_scale(self._scale)
                self._columns_by_key[session.session_key] = column
            else:
                column = maybe_column
                column.set_session(session)
                column.set_scale(self._scale)

            self._layout.removeWidget(column)
            self._layout.insertWidget(index, column)
            self._session_columns.append(column)

        self._overflow_count = max(0, len(ordered_sessions) - MAX_VISIBLE_SESSIONS)
        self._overflow_label.setText(f"+{self._overflow_count}" if self._overflow_count else "")
        self._overflow_label.setVisible(self._overflow_count > 0)
        self._apply_adaptive_column_widths()
        self._position_overflow_label()
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint the recessed session matrix bay."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 10, 10)
        painter.setPen(QPen(QColor(BORDER_COLOR), 1))
        panel = QColor(PANEL_COLOR)
        panel.setAlphaF(0.62)
        painter.setBrush(panel)
        painter.drawPath(path)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        """Keep the overflow marker pinned to the matrix edge."""
        del event
        self._apply_adaptive_column_widths()
        self._position_overflow_label()

    def _position_overflow_label(self) -> None:
        """Place the overflow marker without adding another matrix column."""
        margin = round(BASE_MARGIN * self._scale)
        self._overflow_label.move(
            max(4, self.width() - self._overflow_label.width() - margin),
            margin,
        )

    def _apply_scaled_geometry(self) -> None:
        """Apply scaled matrix padding, spacing, marker, and height."""
        margin = round(BASE_MARGIN * self._scale)
        self._layout.setContentsMargins(margin, margin, margin, margin)
        self._layout.setSpacing(round(COLUMN_SPACING * self._scale))
        self.setMaximumHeight(
            round(COLUMN_HEIGHT * self._scale) + round(MATRIX_VERTICAL_PADDING * self._scale)
        )
        self._overflow_label.setFixedSize(
            round(BASE_OVERFLOW_WIDTH * self._scale),
            round(BASE_OVERFLOW_HEIGHT * self._scale),
        )
        font_size = max(6, round(BASE_OVERFLOW_FONT_SIZE * self._scale))
        self._overflow_label.setFont(QFont("Consolas", font_size, QFont.Bold))

    def _apply_adaptive_column_widths(self) -> None:
        """Give sparse session labels more width without exceeding matrix bounds."""
        if not self._session_columns:
            return
        column_width = self._adaptive_base_column_width(len(self._session_columns))
        for column in self._session_columns:
            column.set_base_column_width(column_width)

    def _adaptive_base_column_width(self, visible_count: int) -> int:
        """Return an unscaled column width based on visible matrix width."""
        if visible_count <= 0:
            return COLUMN_WIDTH

        margin = round(BASE_MARGIN * self._scale)
        spacing = round(COLUMN_SPACING * self._scale)
        overflow_width = self._overflow_label.width() if self._overflow_count else 0
        overflow_gap = spacing if self._overflow_count else 0
        available_width = (
            self.width()
            - margin * 2
            - spacing * max(0, visible_count - 1)
            - overflow_width
            - overflow_gap
        )
        if available_width <= 0:
            return COLUMN_WIDTH
        scaled_column_width = available_width / visible_count
        base_width = round(scaled_column_width / self._scale)
        return max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, base_width))
