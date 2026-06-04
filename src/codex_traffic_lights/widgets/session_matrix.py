"""Expanded-mode multi-session mini traffic-light matrix."""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.widgets.session_column import SessionColumnWidget
from codex_traffic_lights.widgets.traffic_light import BORDER_COLOR, PANEL_COLOR

MAX_VISIBLE_SESSIONS = 5
COLUMN_SPACING = 6


class SessionMatrixWidget(QWidget):
    """Show up to five Codex sessions as adjacent mini traffic-light columns."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create an empty session matrix."""
        super().__init__(parent)
        self._columns_by_key: dict[str, SessionColumnWidget] = {}
        self._session_columns: list[SessionColumnWidget] = []
        self._overflow_count = 0
        self._overflow_label = QLabel("", self)
        self._overflow_label.setObjectName("session_overflow_label")
        self._overflow_label.setAlignment(Qt.AlignCenter)
        self._overflow_label.setFixedSize(28, 18)
        self._overflow_label.setFont(QFont("Consolas", 9, QFont.Bold))
        self._overflow_label.setStyleSheet(
            "color: #6A6A70; background: transparent; border: 1px solid #2A2A30; "
            "border-radius: 8px;"
        )
        self._overflow_label.hide()

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(COLUMN_SPACING)
        self._layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

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
                column.setParent(None)
                column.deleteLater()
                del self._columns_by_key[session_key]

        self._session_columns = []
        for index, session in enumerate(visible_sessions):
            column = self._columns_by_key.get(session.session_key)
            if column is None:
                column = SessionColumnWidget(session)
                self._columns_by_key[session.session_key] = column
            else:
                column.set_session(session)

            self._layout.removeWidget(column)
            self._layout.insertWidget(index, column)
            self._session_columns.append(column)

        self._overflow_count = max(0, len(ordered_sessions) - MAX_VISIBLE_SESSIONS)
        self._overflow_label.setText(f"+{self._overflow_count}" if self._overflow_count else "")
        self._overflow_label.setVisible(self._overflow_count > 0)
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
        self._position_overflow_label()

    def _position_overflow_label(self) -> None:
        """Place the overflow marker without adding another matrix column."""
        self._overflow_label.move(
            max(4, self.width() - self._overflow_label.width() - 8),
            8,
        )
