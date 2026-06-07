"""Pure data definitions for traffic-light effects."""

from __future__ import annotations

from typing import NamedTuple

from codex_traffic_lights.models import CodexStatus, LightMode


class LightEffectParams(NamedTuple):
    """Animation parameters for one traffic light."""

    mode: LightMode
    min_opacity: float
    max_opacity: float
    period_ms: int
    halo_enabled: bool
    halo_spread: int


OFF_EFFECT = LightEffectParams(
    mode=LightMode.OFF,
    min_opacity=0.03,
    max_opacity=0.06,
    period_ms=0,
    halo_enabled=False,
    halo_spread=0,
)
SOLID_EFFECT = LightEffectParams(
    mode=LightMode.SOLID,
    min_opacity=0.95,
    max_opacity=1.0,
    period_ms=0,
    halo_enabled=True,
    halo_spread=8,
)
LOW_POWER_SOLID_EFFECT = LightEffectParams(
    mode=LightMode.SOLID,
    min_opacity=0.95,
    max_opacity=1.0,
    period_ms=0,
    halo_enabled=False,
    halo_spread=0,
)
SLOW_BREATH_EFFECT = LightEffectParams(
    mode=LightMode.SLOW_BREATH,
    min_opacity=0.3,
    max_opacity=1.0,
    period_ms=3000,
    halo_enabled=True,
    halo_spread=12,
)
INTERMITTENT_BLINK_EFFECT = LightEffectParams(
    mode=LightMode.INTERMITTENT_BLINK,
    min_opacity=0.05,
    max_opacity=0.75,
    period_ms=700,
    halo_enabled=True,
    halo_spread=6,
)
SLOW_FLASH_EFFECT = LightEffectParams(
    mode=LightMode.SLOW_FLASH,
    min_opacity=0.08,
    max_opacity=0.95,
    period_ms=2000,
    halo_enabled=True,
    halo_spread=10,
)
FAST_FLASH_EFFECT = LightEffectParams(
    mode=LightMode.FAST_FLASH,
    min_opacity=0.2,
    max_opacity=1.0,
    period_ms=300,
    halo_enabled=True,
    halo_spread=14,
)

STATUS_EFFECTS: dict[
    CodexStatus,
    tuple[LightEffectParams, LightEffectParams, LightEffectParams],
] = {
    CodexStatus.OFFLINE: (SOLID_EFFECT, OFF_EFFECT, OFF_EFFECT),
    CodexStatus.IDLE: (OFF_EFFECT, OFF_EFFECT, LOW_POWER_SOLID_EFFECT),
    CodexStatus.WORKING: (OFF_EFFECT, SLOW_BREATH_EFFECT, OFF_EFFECT),
    CodexStatus.WAITING_APPROVAL: (
        OFF_EFFECT,
        SLOW_FLASH_EFFECT,
        SLOW_FLASH_EFFECT,
    ),
    CodexStatus.WAITING_USER_INPUT: (
        OFF_EFFECT,
        INTERMITTENT_BLINK_EFFECT,
        OFF_EFFECT,
    ),
    CodexStatus.ERROR: (FAST_FLASH_EFFECT, FAST_FLASH_EFFECT, OFF_EFFECT),
}
