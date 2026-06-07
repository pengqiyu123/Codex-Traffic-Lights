"""Tests for shared traffic-light animation timelines."""

from __future__ import annotations

from PyQt5.QtCore import QObject

from codex_traffic_lights.animation.effects import STATUS_EFFECTS
from codex_traffic_lights.animation.timeline import (
    animation_phase_ms,
    create_opacity_timeline,
    opacity_keyframes,
)
from codex_traffic_lights.models import CodexStatus, LightMode


def test_dynamic_opacity_keyframes_are_closed_loops() -> None:
    """Dynamic timelines should return to min opacity before looping."""
    dynamic_effects = [
        effect
        for effects in STATUS_EFFECTS.values()
        for effect in effects
        if effect.mode not in {LightMode.OFF, LightMode.SOLID}
    ]

    for effect in dynamic_effects:
        keyframes = opacity_keyframes(effect)
        assert keyframes[0] == (0.0, effect.min_opacity)
        assert keyframes[-1] == (1.0, effect.min_opacity)
        assert any(opacity == effect.max_opacity for _position, opacity in keyframes)


def test_waiting_approval_green_uses_half_period_phase() -> None:
    """Approval yellow and green slow flashes should alternate instead of syncing."""
    _red, yellow, green = STATUS_EFFECTS[CodexStatus.WAITING_APPROVAL]

    assert animation_phase_ms(CodexStatus.WAITING_APPROVAL, 1, yellow) == 0
    assert animation_phase_ms(CodexStatus.WAITING_APPROVAL, 2, green) == (
        green.period_ms // 2
    )


def test_create_timeline_stores_light_index_and_phase() -> None:
    """Timeline metadata should be available to both main and mini-light widgets."""
    parent = QObject()
    _red, _yellow, green = STATUS_EFFECTS[CodexStatus.WAITING_APPROVAL]

    timeline = create_opacity_timeline(
        green,
        status=CodexStatus.WAITING_APPROVAL,
        light_index=2,
        parent=parent,
    )

    assert timeline is not None
    assert timeline.animation.duration() == green.period_ms
    assert timeline.animation.property("light_index") == 2
    assert timeline.animation.property("phase_ms") == green.period_ms // 2
