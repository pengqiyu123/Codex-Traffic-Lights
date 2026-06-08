"""Expanded-mode mini traffic-light column for one Codex session."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from weakref import ReferenceType, ref

from PyQt5.QtCore import QRectF, Qt, QVariantAnimation
from PyQt5.QtGui import QCloseEvent, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget

from codex_traffic_lights.animation.effects import OFF_EFFECT, STATUS_EFFECTS, LightEffectParams
from codex_traffic_lights.animation.timeline import create_opacity_timeline, start_opacity_timeline
from codex_traffic_lights.models import CodexStatus, LightMode
from codex_traffic_lights.session_models import SessionStatus
from codex_traffic_lights.widgets.traffic_light import LAMP_PALETTE, STATUS_COLORS, _paint_lamp

COLUMN_WIDTH = 44
COLUMN_HEIGHT = 72
MINI_LAMP_DIAMETER = 14
MINI_LAMP_GAP = 4
MIN_COLUMN_WIDTH = 36
MAX_COLUMN_WIDTH = 240
BASE_NAME_FONT_SIZE = 7
BASE_NAME_TOP = 56
BASE_NAME_HEIGHT = 12
BASE_TOP_PADDING = 6
CARD_RADIUS = 6
CARD_MARGIN = 0
CARD_BACKGROUND_COLOR = "#121216"
CARD_BORDER_COLOR = "#2A2A30"
MIN_SCALE = 0.5
MAX_SCALE = 2.0
RETIRING_RED_EFFECT = LightEffectParams(
    mode=LightMode.SLOW_FLASH,
    min_opacity=0.05,
    max_opacity=0.95,
    period_ms=1000,
    halo_enabled=True,
    halo_spread=8,
)

_LAMP_NAMES = ("red", "yellow", "green")


class SessionColumnWidget(QWidget):
    """Render one session as three animated mini lamps plus a compact label."""

    def __init__(self, session: SessionStatus, parent: QWidget | None = None) -> None:
        """Create a session column bound to one session snapshot."""
        super().__init__(parent)
        self._scale = 1.0
        self._base_column_width = COLUMN_WIDTH
        self._session = session
        self._opacities: list[float] = [0.08, 0.08, 0.08]
        self._effects: list[LightEffectParams] = list(STATUS_EFFECTS[session.status])
        self._animations: list[QVariantAnimation] = []
        self._applied_status: CodexStatus | None = None
        self._is_retiring = False
        self._apply_scaled_geometry()
        self.set_session(session)

    @property
    def session(self) -> SessionStatus:
        """Return the session currently displayed by this column."""
        return self._session

    @property
    def status_color(self) -> str:
        """Return the primary color for the session status."""
        return STATUS_COLORS[self._session.status]

    @property
    def has_status_dot(self) -> bool:
        """Return whether this compact column paints an extra status dot."""
        return False

    @property
    def has_card_frame(self) -> bool:
        """Return whether the column paints its own project card frame."""
        return True

    @property
    def card_margin(self) -> int:
        """Return the unscaled inset between the widget edge and card frame."""
        return CARD_MARGIN

    @property
    def has_card_highlight_arc(self) -> bool:
        """Return whether the card paints a decorative highlight arc."""
        return False

    @property
    def mini_lamp_diameter(self) -> int:
        """Return the scaled mini lamp diameter."""
        return max(5, round(MINI_LAMP_DIAMETER * self._scale))

    @property
    def is_retiring(self) -> bool:
        """Return whether this column is showing the UI-only exit cue."""
        return self._is_retiring

    def set_scale(self, scale: float) -> None:
        """Scale column geometry, mini lamps, and label typography."""
        self._scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        self._apply_scaled_geometry()
        self.update()

    def set_base_column_width(self, width: int) -> None:
        """Set the unscaled column width used for adaptive expanded labels."""
        self._base_column_width = max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, width))
        self._apply_scaled_geometry()
        self.update()

    def set_session(self, session: SessionStatus) -> None:
        """Update session data, tooltip, effects, and repaint."""
        self._is_retiring = False
        status_changed = session.status is not self._applied_status
        self._session = session
        if status_changed:
            self._apply_status_effects(session.status)
        self.setToolTip(_tooltip_text(session))
        self.update()

    def set_retiring(self, retiring: bool, session: SessionStatus | None = None) -> None:
        """Show or clear the UI-only disconnected-session exit cue."""
        if not retiring:
            self._is_retiring = False
            if session is not None:
                self.set_session(session)
            return

        self._is_retiring = True
        self._session = replace(self._session, status=CodexStatus.OFFLINE)
        self._stop_animations()
        self._applied_status = None
        self._effects = [RETIRING_RED_EFFECT, OFF_EFFECT, OFF_EFFECT]
        self._start_effect_animations(CodexStatus.OFFLINE)
        self.setToolTip(f"{_tooltip_text(self._session)}\n已断开，3 秒后隐藏")
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
        self._paint_card(painter)

        diameter = self.mini_lamp_diameter
        gap = max(2, round(MINI_LAMP_GAP * self._scale))
        left = (self.width() - diameter) / 2
        lamps_height = diameter * 3 + gap * 2
        label_top = BASE_NAME_TOP * self._scale
        top = max(BASE_TOP_PADDING * self._scale, (label_top - lamps_height) / 2)
        for index, lamp_name in enumerate(_LAMP_NAMES):
            y = top + index * (diameter + gap)
            rect = QRectF(left, y, diameter, diameter)
            _paint_lamp(
                painter,
                rect,
                LAMP_PALETTE[lamp_name],
                self._opacities[index],
                self._effects[index],
            )

        self._paint_name(painter)

    def _paint_card(self, painter: QPainter) -> None:
        """Paint the project card backing for this session."""
        margin = round(CARD_MARGIN * self._scale)
        rect = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        radius = max(4, round(CARD_RADIUS * self._scale))
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(CARD_BACKGROUND_COLOR))
        painter.drawPath(path)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(CARD_BORDER_COLOR), 1))
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)

    def _apply_status_effects(self, status: CodexStatus) -> None:
        """Apply animation effects for the session status."""
        self._stop_animations()
        self._applied_status = status
        self._effects = list(STATUS_EFFECTS[status])
        self._start_effect_animations(status)

    def _start_effect_animations(self, status: CodexStatus) -> None:
        """Start animation timelines for the currently configured effects."""
        for light_index, effect in enumerate(self._effects):
            if effect.mode in {LightMode.OFF, LightMode.SOLID} or effect.period_ms <= 0:
                self._opacities[light_index] = effect.max_opacity
                continue

            self._opacities[light_index] = effect.min_opacity
            timeline = create_opacity_timeline(
                effect,
                status=status,
                light_index=light_index,
                parent=self,
            )
            if timeline is None:
                continue
            column_ref = ref(self)
            timeline.animation.valueChanged.connect(
                lambda value=0.0, index=light_index, target=column_ref: (
                    _apply_animation_value(target, index, value)
                )
            )
            self._animations.append(timeline.animation)
            start_opacity_timeline(timeline)

    def _paint_name(self, painter: QPainter) -> None:
        """Paint the single-line truncated session name."""
        font = QFont("Consolas", max(5, round(BASE_NAME_FONT_SIZE * self._scale)))
        font.setFamilies(["Consolas", "JetBrains Mono", "Source Code Pro"])
        painter.setFont(font)
        painter.setPen(QPen(QColor("#8A8A8F")))
        metrics = QFontMetrics(font)
        margin = max(2, round(2 * self._scale))
        text = metrics.elidedText(
            self._session.display_name,
            Qt.ElideRight,
            self.width() - margin * 2,
        )
        painter.drawText(
            QRectF(
                margin,
                BASE_NAME_TOP * self._scale,
                self.width() - margin * 2,
                BASE_NAME_HEIGHT * self._scale,
            ),
            Qt.AlignCenter,
            text,
        )

    def _apply_scaled_geometry(self) -> None:
        """Apply scaled fixed column geometry."""
        self.setFixedSize(
            round(self._base_column_width * self._scale),
            round(COLUMN_HEIGHT * self._scale),
        )

    def _stop_animations(self) -> None:
        """Stop and forget mini-lamp animations."""
        for animation in self._animations:
            animation.stop()
        self._animations.clear()

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        """Stop mini-lamp animations when the column is closed."""
        self._stop_animations()
        super().closeEvent(event)


def _apply_animation_value(
    column_ref: ReferenceType[SessionColumnWidget],
    light_index: int,
    value: object,
) -> None:
    """Apply one QVariantAnimation value without keeping the column alive."""
    column = column_ref()
    if column is None:
        return
    column.set_light_opacity(light_index, _animation_float(value))


def _animation_float(value: object) -> float:
    """Return a float for a QVariantAnimation value."""
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))


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
