"""Shared opacity animation timelines for traffic-light widgets."""

from __future__ import annotations

from typing import NamedTuple

from PyQt5.QtCore import QEasingCurve, QObject, QVariantAnimation

from codex_traffic_lights.animation.effects import LightEffectParams
from codex_traffic_lights.models import CodexStatus, LightMode


class AnimationTimeline(NamedTuple):
    """Animation object plus phase metadata for one light."""

    animation: QVariantAnimation
    phase_ms: int


def create_opacity_timeline(
    effect: LightEffectParams,
    *,
    status: CodexStatus,
    light_index: int,
    parent: QObject,
) -> AnimationTimeline | None:
    """Create a configured opacity animation for one light effect."""
    if effect.period_ms <= 0 or effect.mode in {LightMode.OFF, LightMode.SOLID}:
        return None

    animation = QVariantAnimation(parent)
    animation.setDuration(effect.period_ms)
    animation.setLoopCount(-1)
    animation.setEasingCurve(QEasingCurve.InOutSine)
    for position, opacity in opacity_keyframes(effect):
        animation.setKeyValueAt(position, opacity)

    phase_ms = animation_phase_ms(status, light_index, effect)
    animation.setProperty("light_index", light_index)
    animation.setProperty("phase_ms", phase_ms)
    return AnimationTimeline(animation=animation, phase_ms=phase_ms)


def start_opacity_timeline(timeline: AnimationTimeline) -> None:
    """Start one timeline and seek to its phase offset."""
    timeline.animation.start()
    if timeline.phase_ms:
        timeline.animation.setCurrentTime(timeline.phase_ms)


def opacity_keyframes(effect: LightEffectParams) -> tuple[tuple[float, float], ...]:
    """Return a closed-loop opacity curve for a dynamic effect."""
    if effect.mode is LightMode.SLOW_BREATH:
        return (
            (0.0, effect.min_opacity),
            (0.5, effect.max_opacity),
            (1.0, effect.min_opacity),
        )
    if effect.mode is LightMode.SLOW_FLASH:
        return (
            (0.0, effect.min_opacity),
            (0.18, effect.max_opacity),
            (0.48, effect.max_opacity),
            (0.66, effect.min_opacity),
            (1.0, effect.min_opacity),
        )
    if effect.mode is LightMode.INTERMITTENT_BLINK:
        return (
            (0.0, effect.min_opacity),
            (0.06, effect.max_opacity),
            (0.5, effect.max_opacity),
            (0.56, effect.min_opacity),
            (1.0, effect.min_opacity),
        )
    if effect.mode is LightMode.FAST_FLASH:
        return (
            (0.0, effect.min_opacity),
            (0.18, effect.max_opacity),
            (0.5, effect.max_opacity),
            (0.68, effect.min_opacity),
            (1.0, effect.min_opacity),
        )
    return ((0.0, effect.min_opacity), (1.0, effect.max_opacity))


def animation_phase_ms(
    status: CodexStatus,
    light_index: int,
    effect: LightEffectParams,
) -> int:
    """Return the phase offset for status-specific multi-light effects."""
    if (
        status is CodexStatus.WAITING_APPROVAL
        and effect.mode is LightMode.SLOW_FLASH
        and light_index == 2
    ):
        return effect.period_ms // 2
    return 0
