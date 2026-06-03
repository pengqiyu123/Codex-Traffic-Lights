"""Traffic-light painter widget."""

from __future__ import annotations

from typing import overload

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QRadialGradient
from PyQt5.QtWidgets import QWidget

from codex_traffic_lights.animation.effects import LightEffectParams
from codex_traffic_lights.models import LightMode

RED_BRIGHT = QColor("#FF4444")
RED_DIM = QColor("#3A1111")
YELLOW_BRIGHT = QColor("#FFD700")
YELLOW_DIM = QColor("#3A3300")
GREEN_BRIGHT = QColor("#44FF44")
GREEN_DIM = QColor("#113A11")


class TrafficLightWidget(QWidget):
    """Paint red, yellow, and green lights with opacity and halo state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a traffic-light painter widget."""
        super().__init__(parent)
        self.setMinimumSize(80, 120)
        self._opacities: list[float] = [1.0, 0.15, 0.15]
        self._effects: list[LightEffectParams | None] = [None, None, None]

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
        """Paint the three lights and their halos."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        lights = [
            (RED_BRIGHT, RED_DIM, self._opacities[0], self._effects[0]),
            (YELLOW_BRIGHT, YELLOW_DIM, self._opacities[1], self._effects[1]),
            (GREEN_BRIGHT, GREEN_DIM, self._opacities[2], self._effects[2]),
        ]
        diameter = min(40, max(24, int(self.width() * 0.52)))
        gap = 14
        total_height = diameter * 3 + gap * 2
        top = max(0, (self.height() - total_height) / 2)
        left = (self.width() - diameter) / 2

        for index, (bright, dim, opacity, effect) in enumerate(lights):
            y = top + index * (diameter + gap)
            rect = QRectF(left, y, diameter, diameter)
            center = QPointF(rect.center())
            if _halo_enabled(effect, opacity):
                spread = effect.halo_spread if effect is not None else 8
                halo_radius = diameter / 2 + spread
                gradient = QRadialGradient(center, halo_radius)
                halo_color = QColor(bright)
                halo_color.setAlphaF(min(0.35, opacity * 0.30))
                gradient.setColorAt(0.0, halo_color)
                gradient.setColorAt(
                    1.0,
                    QColor(
                        halo_color.red(),
                        halo_color.green(),
                        halo_color.blue(),
                        0,
                    ),
                )
                painter.fillRect(
                    QRectF(
                        center.x() - halo_radius,
                        center.y() - halo_radius,
                        halo_radius * 2,
                        halo_radius * 2,
                    ),
                    gradient,
                )

            painter.setPen(Qt.NoPen)
            painter.setBrush(dim)
            painter.drawEllipse(rect)
            active_color = QColor(bright)
            active_color.setAlphaF(opacity)
            painter.setBrush(active_color)
            painter.drawEllipse(rect)

    def _set_single_opacity(self, light_index: int, opacity: float) -> None:
        """Set one light opacity and repaint."""
        if not 0 <= light_index < 3:
            raise IndexError("light_index must be 0, 1, or 2")
        self._opacities[light_index] = _clamp_opacity(opacity)
        self.update()


def _clamp_opacity(opacity: float) -> float:
    """Clamp opacity to the painter-supported 0-1 range."""
    return max(0.0, min(1.0, opacity))


def _halo_enabled(effect: LightEffectParams | None, opacity: float) -> bool:
    """Return True when an effect should paint a halo."""
    return (
        effect is not None
        and effect.halo_enabled
        and effect.mode is not LightMode.OFF
        and opacity > 0.18
    )
