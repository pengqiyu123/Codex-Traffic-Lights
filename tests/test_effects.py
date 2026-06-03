"""Tests for traffic-light effect presets."""

from __future__ import annotations

import pytest

from codex_traffic_lights.animation.effects import STATUS_EFFECTS, LightEffectParams
from codex_traffic_lights.models import CodexStatus, LightMode


def test_status_effects_cover_all_codex_statuses() -> None:
    """Every product status should have a three-light effect preset."""
    assert set(STATUS_EFFECTS) == set(CodexStatus)


def test_each_status_has_three_legal_light_effects() -> None:
    """Each status should define red, yellow, and green effects with legal values."""
    for effects in STATUS_EFFECTS.values():
        assert len(effects) == 3
        for effect in effects:
            assert isinstance(effect, LightEffectParams)
            assert isinstance(effect.mode, LightMode)
            assert 0.0 <= effect.min_opacity <= 1.0
            assert 0.0 <= effect.max_opacity <= 1.0
            assert effect.min_opacity <= effect.max_opacity
            assert effect.period_ms >= 0
            assert effect.halo_spread >= 0


@pytest.mark.parametrize(
    ("mode", "min_opacity", "max_opacity", "period_ms"),
    [
        (LightMode.OFF, 0.08, 0.12, 0),
        (LightMode.SOLID, 0.95, 1.0, 0),
        (LightMode.SLOW_BREATH, 0.3, 1.0, 3000),
        (LightMode.INTERMITTENT_BLINK, 0.1, 0.6, 1000),
        (LightMode.SLOW_FLASH, 0.2, 0.8, 2000),
        (LightMode.FAST_FLASH, 0.2, 1.0, 300),
    ],
)
def test_effect_params_match_prd_mode_values(
    mode: LightMode,
    min_opacity: float,
    max_opacity: float,
    period_ms: int,
) -> None:
    """Mode presets should match the numeric values in the PRD."""
    matching_effect = next(
        effect
        for effects in STATUS_EFFECTS.values()
        for effect in effects
        if effect.mode is mode
    )

    assert matching_effect.min_opacity == min_opacity
    assert matching_effect.max_opacity == max_opacity
    assert matching_effect.period_ms == period_ms


def test_offline_status_has_only_red_light_active() -> None:
    """OFFLINE should show only the red light."""
    red, yellow, green = STATUS_EFFECTS[CodexStatus.OFFLINE]

    assert red.mode is not LightMode.OFF
    assert yellow.mode is LightMode.OFF
    assert green.mode is LightMode.OFF


def test_idle_status_has_only_green_light_active() -> None:
    """IDLE should show only the green light."""
    red, yellow, green = STATUS_EFFECTS[CodexStatus.IDLE]

    assert red.mode is LightMode.OFF
    assert yellow.mode is LightMode.OFF
    assert green.mode is not LightMode.OFF


def test_idle_green_light_has_no_halo() -> None:
    """IDLE should look like a low-power steady indicator without an outer halo."""
    _, _, green = STATUS_EFFECTS[CodexStatus.IDLE]

    assert green.halo_enabled is False


def test_waiting_approval_status_has_yellow_and_green_active() -> None:
    """WAITING_APPROVAL should flash yellow and green together."""
    red, yellow, green = STATUS_EFFECTS[CodexStatus.WAITING_APPROVAL]

    assert red.mode is LightMode.OFF
    assert yellow.mode is not LightMode.OFF
    assert green.mode is not LightMode.OFF
