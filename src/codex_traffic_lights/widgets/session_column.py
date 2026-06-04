"""Expanded-mode mini traffic-light column for one Codex session."""

from __future__ import annotations

import datetime as dt

from PyQt5.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from codex_traffic_lights.animation.effects import STATUS_EFFECTS, LightEffectParams
from codex_traffic_lights.models import CodexStatus, LightMode
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.widgets.traffic_light import LAMP_PALETTE, STATUS_COLORS, _paint_lamp

COLUMN_WIDTH = 44
COLUMN_HEIGHT = 68
MINI_LAMP_DIAMETER = 10
MINI_LAMP_GAP = 4
STATUS_DOT_DIAMETER = 6

_LAMP_NAMES = ("red", "yellow", "green")


class SessionColumnWidget(QWidget):
    """Render one session as three animated mini lamps plus a compact label."""

    def __init__(self, session: SessionStatus, parent: QWidget | None = None) -> None:
        """Create a session column bound to one session snapshot."""
        super().__init__(parent)
        self.setFixedWidth(COLUMN_WIDTH)
        self.setMinimumHeight(COLUMN_HEIGHT)
        self._session = session
        self._opacities: list[float] = [0.08, 0.08, 0.08]
        self._effects: list[LightEffectParams] = list(STATUS_EFFECTS[session.status])
        self._animations: list[QVariantAnimation] = []
        self.set_session(session)

    @property
    def session(self) -> SessionStatus:
        """Return the session currently displayed by this column."""
        return self._session

    @property
    def status_color(self) -> str:
        """Return the primary color for the session status."""
        return STATUS_COLORS[self._session.status]

    def set_session(self, session: SessionStatus) -> None:
        """Update session data, tooltip, effects, and repaint."""
        self._session = session
        self._apply_status_effects(session.status)
        self.setToolTip(_tooltip_text(session))
        self.update()

    def set_light_opacity(self, light_index: int, opacity: float) -> None:
        """Set opacity for one mini lamp from an animation callback."""
        if not 0 <= light_index < 3:
            raise IndexError("light_index must be 0, 1, or 2")
        self._opacities[light_index] = max(0.0, min(1.0, opacity))
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint the mini traffic-light column."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        left = (self.width() - MINI_LAMP_DIAMETER) / 2
        top = 4.0
        for index, lamp_name in enumerate(_LAMP_NAMES):
            y = top + index * (MINI_LAMP_DIAMETER + MINI_LAMP_GAP)
            rect = QRectF(left, y, MINI_LAMP_DIAMETER, MINI_LAMP_DIAMETER)
            _paint_lamp(
                painter,
                rect,
                LAMP_PALETTE[lamp_name],
                self._opacities[index],
                self._effects[index],
            )

        self._paint_name(painter)
        self._paint_status_dot(painter)

    def _apply_status_effects(self, status: CodexStatus) -> None:
        """Apply animation effects for the session status."""
        self._stop_animations()
        self._effects = list(STATUS_EFFECTS[status])
        for light_index, effect in enumerate(self._effects):
            if effect.mode in {LightMode.OFF, LightMode.SOLID} or effect.period_ms <= 0:
                self._opacities[light_index] = effect.max_opacity
                continue

            self._opacities[light_index] = effect.min_opacity
            animation = QVariantAnimation(self)
            animation.setStartValue(effect.min_opacity)
            animation.setEndValue(effect.max_opacity)
            animation.setDuration(effect.period_ms)
            animation.setLoopCount(-1)
            animation.setEasingCurve(QEasingCurve.InOutSine)
            animation.valueChanged.connect(
                lambda value, index=light_index: self.set_light_opacity(index, float(value))
            )
            self._animations.append(animation)
            animation.start()

    def _paint_name(self, painter: QPainter) -> None:
        """Paint the single-line truncated session name."""
        font = QFont("Consolas", 7)
        font.setFamilies(["Consolas", "JetBrains Mono", "Source Code Pro"])
        painter.setFont(font)
        painter.setPen(QPen(QColor("#8A8A8F")))
        metrics = QFontMetrics(font)
        text = metrics.elidedText(self._session.display_name, Qt.ElideRight, self.width() - 4)
        painter.drawText(QRectF(2, 44, self.width() - 4, 12), Qt.AlignCenter, text)

    def _paint_status_dot(self, painter: QPainter) -> None:
        """Paint the compact status color dot under the name."""
        dot_color = QColor(self.status_color)
        dot_color.setAlphaF(0.9)
        painter.setBrush(dot_color)
        painter.setPen(Qt.NoPen)
        left = (self.width() - STATUS_DOT_DIAMETER) / 2
        painter.drawEllipse(QRectF(left, 59, STATUS_DOT_DIAMETER, STATUS_DOT_DIAMETER))

    def _stop_animations(self) -> None:
        """Stop and forget mini-lamp animations."""
        for animation in self._animations:
            animation.stop()
        self._animations.clear()


def _tooltip_text(session: SessionStatus) -> str:
    """Build the full expanded-mode tooltip for one session."""
    updated = dt.datetime.fromtimestamp(session.last_updated).strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"{session.display_name}\n"
        f"endpoint: {session.endpoint_id}\n"
        f"threadId: {session.thread_id}\n"
        f"状态: {session.status.label}\n"
        f"更新: {updated}"
    )
