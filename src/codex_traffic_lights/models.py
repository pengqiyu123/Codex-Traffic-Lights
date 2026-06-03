"""Core immutable data models for Codex Traffic Lights."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LightMode(Enum):
    """Animation mode for a single traffic light."""

    OFF = "off"
    SOLID = "solid"
    SLOW_BREATH = "slow_breath"
    INTERMITTENT_BLINK = "intermittent_blink"
    SLOW_FLASH = "slow_flash"
    FAST_FLASH = "fast_flash"


@dataclass(frozen=True)
class LightState:
    """Three-light state for one Codex status."""

    red: LightMode
    yellow: LightMode
    green: LightMode


class CodexStatus(Enum):
    """Product-facing Codex status mapped from audited Codex app-server signals."""

    OFFLINE = (
        "待机离线",
        LightState(LightMode.SOLID, LightMode.OFF, LightMode.OFF),
    )
    IDLE = (
        "空闲待命",
        LightState(LightMode.OFF, LightMode.OFF, LightMode.SOLID),
    )
    WORKING = (
        "正在工作",
        LightState(LightMode.OFF, LightMode.SLOW_BREATH, LightMode.OFF),
    )
    WAITING_APPROVAL = (
        "待审批确认",
        LightState(LightMode.OFF, LightMode.SLOW_FLASH, LightMode.SLOW_FLASH),
    )
    WAITING_USER_INPUT = (
        "待用户输入",
        LightState(LightMode.OFF, LightMode.INTERMITTENT_BLINK, LightMode.OFF),
    )
    ERROR = (
        "运行异常",
        LightState(LightMode.FAST_FLASH, LightMode.FAST_FLASH, LightMode.OFF),
    )

    def __init__(self, label: str, light_state: LightState) -> None:
        """Store user-facing label and light-state metadata."""
        self._label = label
        self._light_state = light_state

    @property
    def label(self) -> str:
        """Chinese user-facing status label."""
        return self._label

    @property
    def light_state(self) -> LightState:
        """Traffic-light mode tuple for this status."""
        return self._light_state


@dataclass(frozen=True)
class AppConfig:
    """Persistent application configuration."""

    poll_interval_ms: int = 2000
    codex_process_name: str = "codex"
    app_server_url: str | None = None
    window_scale: float = 1.0
    notification_enabled: bool = True
    sound_enabled: bool = True
