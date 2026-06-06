"""PyQt animation engine for traffic-light opacity changes."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from weakref import ReferenceType, ref

from PyQt5.QtCore import QEasingCurve, QVariantAnimation
from PyQt5.QtWidgets import QWidget

from codex_traffic_lights.animation.effects import STATUS_EFFECTS, LightEffectParams
from codex_traffic_lights.models import CodexStatus, LightMode


class LightAnimationEngine:
    """Drive traffic-light opacity animations for a QWidget-based light display."""

    def __init__(self, traffic_light_widget: QWidget) -> None:
        """Create an engine bound to the traffic-light widget."""
        self.traffic_light_widget = traffic_light_widget
        self._animations: list[QVariantAnimation] = []

    def set_status(self, status: CodexStatus) -> None:
        """Stop current animations and apply the effect preset for a status."""
        self._stop_all()
        for light_index, effect in enumerate(STATUS_EFFECTS[status]):
            self._apply_effect(light_index, effect)
            animation = self._create_animation(effect)
            if animation is None:
                self._apply_opacity(light_index, effect.max_opacity)
                continue

            self._apply_opacity(light_index, effect.min_opacity)
            engine_ref = ref(self)
            animation.valueChanged.connect(
                lambda value=0.0, index=light_index, target=engine_ref: (
                    _apply_animation_value(target, index, value)
                )
            )
            self._animations.append(animation)
            animation.start()

    def _create_animation(self, effect: LightEffectParams) -> QVariantAnimation | None:
        """Create a QVariantAnimation for dynamic effects."""
        if effect.period_ms <= 0 or effect.mode in {LightMode.OFF, LightMode.SOLID}:
            return None

        animation = QVariantAnimation(self.traffic_light_widget)
        animation.setStartValue(effect.min_opacity)
        animation.setEndValue(effect.max_opacity)
        animation.setDuration(effect.period_ms)
        animation.setLoopCount(-1)
        animation.setEasingCurve(QEasingCurve.InOutSine)
        return animation

    def _stop_all(self) -> None:
        """Stop and forget all active animations."""
        for animation in self._animations:
            animation.stop()
        self._animations.clear()

    def _apply_effect(self, light_index: int, effect: LightEffectParams) -> None:
        """Apply effect metadata to the widget."""
        self.traffic_light_widget.setProperty(f"light_{light_index}_mode", effect.mode.value)
        self.traffic_light_widget.setProperty(
            f"light_{light_index}_min_opacity",
            effect.min_opacity,
        )
        self.traffic_light_widget.setProperty(
            f"light_{light_index}_max_opacity",
            effect.max_opacity,
        )
        self.traffic_light_widget.setProperty(f"light_{light_index}_period_ms", effect.period_ms)
        self.traffic_light_widget.setProperty(
            f"light_{light_index}_halo_enabled",
            effect.halo_enabled,
        )
        self.traffic_light_widget.setProperty(
            f"light_{light_index}_halo_spread",
            effect.halo_spread,
        )

        set_light_effect = getattr(self.traffic_light_widget, "set_light_effect", None)
        if callable(set_light_effect):
            callback = cast(Callable[[int, LightEffectParams], None], set_light_effect)
            callback(light_index, effect)

    def _apply_opacity(self, light_index: int, opacity: float) -> None:
        """Apply light opacity to the widget and request repaint."""
        self.traffic_light_widget.setProperty(f"light_{light_index}_opacity", opacity)

        set_light_opacity = getattr(self.traffic_light_widget, "set_light_opacity", None)
        if callable(set_light_opacity):
            callback = cast(Callable[[int, float], None], set_light_opacity)
            callback(light_index, opacity)

        self.traffic_light_widget.update()


def _apply_animation_value(
    engine_ref: ReferenceType[LightAnimationEngine],
    light_index: int,
    value: object,
) -> None:
    """Apply one QVariantAnimation value without keeping the engine alive."""
    engine = engine_ref()
    if engine is None:
        return
    engine._apply_opacity(light_index, _animation_float(value))


def _animation_float(value: object) -> float:
    """Return a float for a QVariantAnimation value."""
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))
