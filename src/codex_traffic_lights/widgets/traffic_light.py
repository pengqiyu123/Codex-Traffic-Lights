"""Traffic-light painter widget."""

from __future__ import annotations

from dataclasses import dataclass
from typing import overload

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt5.QtWidgets import QWidget

from codex_traffic_lights.animation.effects import LightEffectParams
from codex_traffic_lights.models import LightMode

BODY_BACKGROUND_COLOR = "#0D0D0F"
PANEL_COLOR = "#16161A"
BORDER_COLOR = "#2A2A30"
HIGHLIGHT_BORDER_COLOR = "#3A3A42"
GROOVE_COLOR = "#08080A"


@dataclass(frozen=True)
class LampPalette:
    """Color palette for one physical lamp."""

    bright: str
    dim: str
    halo_rgba: tuple[int, int, int, float]


LAMP_PALETTE: dict[str, LampPalette] = {
    "red": LampPalette("#FF3B30", "#2A0808", (255, 59, 48, 0.25)),
    "yellow": LampPalette("#FFCC00", "#2A2400", (255, 204, 0, 0.25)),
    "green": LampPalette("#34C759", "#082A10", (52, 199, 89, 0.25)),
}

_LAMP_ORDER = ("red", "yellow", "green")


class TrafficLightWidget(QWidget):
    """Paint red, yellow, and green lights with opacity and halo state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a traffic-light painter widget."""
        super().__init__(parent)
        self.setMinimumSize(72, 120)
        self._opacities: list[float] = [1.0, 0.1, 0.1]
        self._effects: list[LightEffectParams | None] = [None, None, None]
        self._lamp_diameter: int | None = None

    def set_lamp_diameter(self, diameter: int | None) -> None:
        """Set an explicit lamp diameter, or None to use compact auto sizing."""
        self._lamp_diameter = diameter
        self.update()

    @property
    def red_opacity(self) -> float:
        """Return red light opacity."""
        return self._opacities[0]

    @red_opacity.setter
    def red_opacity(self, opacity: float) -> None:
        self._set_single_opacity(0, opacity)

    @property
    def yellow_opacity(self) -> float:
        """Return yellow light opacity."""
        return self._opacities[1]

    @yellow_opacity.setter
    def yellow_opacity(self, opacity: float) -> None:
        self._set_single_opacity(1, opacity)

    @property
    def green_opacity(self) -> float:
        """Return green light opacity."""
        return self._opacities[2]

    @green_opacity.setter
    def green_opacity(self, opacity: float) -> None:
        self._set_single_opacity(2, opacity)

    @overload
    def set_light_opacity(self, red: float, yellow: float, green: float) -> None:
        ...

    @overload
    def set_light_opacity(self, light_index: int, opacity: float) -> None:
        ...

    def set_light_opacity(
        self,
        first: float | int,
        second: float | None = None,
        third: float | None = None,
    ) -> None:
        """Set all light opacities, or update one light by index for animations."""
        if isinstance(first, int) and second is not None and third is None:
            self._set_single_opacity(first, second)
            return
        if second is not None and third is not None:
            self._opacities = [
                _clamp_opacity(float(first)),
                _clamp_opacity(second),
                _clamp_opacity(third),
            ]
            self.update()
            return
        raise TypeError("set_light_opacity expects three opacities or an index and opacity")

    def set_light_effect(self, light_index: int, effect: LightEffectParams) -> None:
        """Set effect metadata for one light."""
        if not 0 <= light_index < 3:
            raise IndexError("light_index must be 0, 1, or 2")
        self._effects[light_index] = effect
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Paint the three lights as layered glass-covered hardware indicators."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        diameter = self._lamp_diameter or min(36, max(28, int(self.width() * 0.50)))
        gap = 8 if self._lamp_diameter is not None else 12
        total_height = diameter * 3 + gap * 2
        top = max(0, (self.height() - total_height) / 2)
        left = (self.width() - diameter) / 2

        for index, lamp_name in enumerate(_LAMP_ORDER):
            palette = LAMP_PALETTE[lamp_name]
            opacity = self._opacities[index]
            effect = self._effects[index]
            y = top + index * (diameter + gap)
            rect = QRectF(left, y, diameter, diameter)
            _paint_lamp(painter, rect, palette, opacity, effect)

    def _set_single_opacity(self, light_index: int, opacity: float) -> None:
        """Set one light opacity and repaint."""
        if not 0 <= light_index < 3:
            raise IndexError("light_index must be 0, 1, or 2")
        self._opacities[light_index] = _clamp_opacity(opacity)
        self.update()


def _clamp_opacity(opacity: float) -> float:
    """Clamp opacity to the painter-supported 0-1 range."""
    return max(0.0, min(1.0, opacity))


def _rgba_color(rgba: tuple[int, int, int, float], alpha_multiplier: float = 1.0) -> QColor:
    """Create a QColor from an RGBA tuple with optional alpha scaling."""
    red, green, blue, alpha = rgba
    color = QColor(red, green, blue)
    color.setAlphaF(max(0.0, min(1.0, alpha * alpha_multiplier)))
    return color


def _halo_enabled(effect: LightEffectParams | None, opacity: float) -> bool:
    """Return True when an effect should paint a halo."""
    return (
        effect is not None
        and effect.halo_enabled
        and effect.mode is not LightMode.OFF
        and opacity > 0.18
    )


def _lit_opacity(effect: LightEffectParams | None, opacity: float) -> float:
    """Return the visible lit layer opacity, suppressing it for OFF lamps."""
    if effect is not None and effect.mode is LightMode.OFF:
        return 0.0
    return _clamp_opacity(opacity)


def _paint_groove(painter: QPainter, rect: QRectF) -> None:
    """Paint the recessed circular socket behind a lamp."""
    groove_rect = rect.adjusted(-4, -4, 4, 4)
    groove_gradient = QRadialGradient(groove_rect.center(), groove_rect.width() / 2)
    groove_gradient.setColorAt(0.0, QColor("#111115"))
    groove_gradient.setColorAt(0.72, QColor(GROOVE_COLOR))
    groove_gradient.setColorAt(1.0, QColor("#020203"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(groove_gradient)
    painter.drawEllipse(groove_rect)


def _paint_dim_glass(painter: QPainter, rect: QRectF, palette: LampPalette) -> None:
    """Paint the deep unlit lamp glass color."""
    dim_gradient = QRadialGradient(rect.center(), rect.width() / 2)
    dim_gradient.setColorAt(0.0, QColor(palette.dim).lighter(125))
    dim_gradient.setColorAt(0.68, QColor(palette.dim))
    dim_gradient.setColorAt(1.0, QColor("#040405"))
    painter.setBrush(dim_gradient)
    painter.drawEllipse(rect)


def _paint_lit_core(
    painter: QPainter,
    rect: QRectF,
    palette: LampPalette,
    opacity: float,
) -> None:
    """Paint the bright internal radial lamp glow."""
    if opacity <= 0.0:
        return

    bright = QColor(palette.bright)
    bright.setAlphaF(min(1.0, opacity))
    mid = QColor(palette.bright)
    mid.setAlphaF(min(0.82, opacity * 0.68))
    edge = QColor(palette.dim)
    edge.setAlphaF(min(0.75, opacity * 0.28))

    glow = QRadialGradient(
        QPointF(rect.center().x() - rect.width() * 0.12, rect.center().y() - rect.height() * 0.14),
        rect.width() * 0.58,
    )
    glow.setColorAt(0.0, bright)
    glow.setColorAt(0.45, mid)
    glow.setColorAt(1.0, edge)
    painter.setBrush(glow)
    painter.drawEllipse(rect.adjusted(2, 2, -2, -2))


def _paint_inner_glow(
    painter: QPainter,
    rect: QRectF,
    palette: LampPalette,
    opacity: float,
) -> None:
    """Paint the colored rim caused by light catching the glass edge."""
    if opacity <= 0.0:
        return

    rim_color = QColor(palette.bright)
    rim_color.setAlphaF(min(0.65, opacity * 0.45))
    pen = QPen(rim_color, 2)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(rect.adjusted(2, 2, -2, -2))
    painter.setPen(Qt.NoPen)


def _paint_highlight(painter: QPainter, rect: QRectF) -> None:
    """Paint the fixed glass reflection highlight."""
    highlight_rect = QRectF(
        rect.left() + rect.width() * 0.26,
        rect.top() + rect.height() * 0.18,
        rect.width() * 0.20,
        rect.height() * 0.13,
    )
    path = QPainterPath()
    path.addEllipse(highlight_rect)
    color = QColor(255, 255, 255)
    color.setAlphaF(0.58)
    painter.fillPath(path, color)


def _paint_halo(
    painter: QPainter,
    rect: QRectF,
    palette: LampPalette,
    opacity: float,
    effect: LightEffectParams | None,
) -> None:
    """Paint the lamp spill outside the glass when the effect enables halo."""
    if not _halo_enabled(effect, opacity):
        return

    spread = effect.halo_spread if effect is not None else 8
    radius = rect.width() / 2 + spread
    halo = QRadialGradient(rect.center(), radius)
    halo.setColorAt(0.0, _rgba_color(palette.halo_rgba, opacity))
    halo.setColorAt(0.62, _rgba_color(palette.halo_rgba, opacity * 0.32))
    halo.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setBrush(halo)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(
        QRectF(
            rect.center().x() - radius,
            rect.center().y() - radius,
            radius * 2,
            radius * 2,
        )
    )


def _paint_bezel(painter: QPainter, rect: QRectF) -> None:
    """Paint the thin metallic retaining ring around a lamp."""
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(BORDER_COLOR), 1))
    painter.drawEllipse(rect.adjusted(-1, -1, 1, 1))
    painter.setPen(QPen(QColor(HIGHLIGHT_BORDER_COLOR), 1))
    painter.drawArc(rect.adjusted(-1, -1, 1, 1), 45 * 16, 95 * 16)
    painter.setPen(Qt.NoPen)


def _paint_lamp(
    painter: QPainter,
    rect: QRectF,
    palette: LampPalette,
    opacity: float,
    effect: LightEffectParams | None,
) -> None:
    """Paint one complete lamp using the seven-layer instrument spec."""
    lit_opacity = _lit_opacity(effect, opacity)
    _paint_halo(painter, rect, palette, lit_opacity, effect)
    _paint_groove(painter, rect)
    _paint_dim_glass(painter, rect, palette)
    _paint_lit_core(painter, rect, palette, lit_opacity)
    _paint_highlight(painter, rect)
    _paint_inner_glow(painter, rect, palette, lit_opacity)
    _paint_bezel(painter, rect)
