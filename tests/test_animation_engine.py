"""Tests for the PyQt light animation engine."""

from __future__ import annotations

import pytest
from PyQt5.QtCore import QAbstractAnimation
from PyQt5.QtWidgets import QApplication, QWidget

from codex_traffic_lights.animation.effects import STATUS_EFFECTS, LightEffectParams
from codex_traffic_lights.animation.engine import LightAnimationEngine
from codex_traffic_lights.models import CodexStatus


class RecordingTrafficLightWidget(QWidget):
    """Traffic-light widget stand-in that records engine updates."""

    def __init__(self) -> None:
        """Create empty update logs."""
        super().__init__()
        self.effect_updates: list[tuple[int, LightEffectParams]] = []
        self.opacity_updates: list[tuple[int, float]] = []

    def set_light_effect(self, light_index: int, effect: LightEffectParams) -> None:
        """Record effect metadata sent by the engine."""
        self.effect_updates.append((light_index, effect))

    def set_light_opacity(self, light_index: int, opacity: float) -> None:
        """Record opacity values sent by the engine."""
        self.opacity_updates.append((light_index, opacity))


@pytest.fixture(scope="session", autouse=True)
def qapplication() -> QApplication:
    """Ensure QWidget-based tests have a QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_set_status_applies_effect_metadata_for_three_lights() -> None:
    """set_status should apply red, yellow, and green effect metadata."""
    widget = RecordingTrafficLightWidget()
    engine = LightAnimationEngine(widget)

    engine.set_status(CodexStatus.IDLE)

    assert widget.effect_updates == list(enumerate(STATUS_EFFECTS[CodexStatus.IDLE]))


def test_set_status_creates_running_animation_for_dynamic_effect() -> None:
    """Dynamic effects should be represented by running QVariantAnimation objects."""
    widget = RecordingTrafficLightWidget()
    engine = LightAnimationEngine(widget)

    engine.set_status(CodexStatus.WORKING)

    assert len(engine._animations) == 1
    animation = engine._animations[0]
    assert animation.duration() == STATUS_EFFECTS[CodexStatus.WORKING][1].period_ms
    assert animation.state() == QAbstractAnimation.Running


def test_waiting_approval_main_lights_alternate_phase() -> None:
    """Approval yellow and green lamps should use alternating slow-flash phases."""
    widget = RecordingTrafficLightWidget()
    engine = LightAnimationEngine(widget)

    engine.set_status(CodexStatus.WAITING_APPROVAL)

    assert len(engine._animations) == 2
    assert [animation.property("light_index") for animation in engine._animations] == [1, 2]
    assert [animation.property("phase_ms") for animation in engine._animations] == [0, 1000]


def test_set_status_stops_existing_animations_before_starting_new_status() -> None:
    """Changing status should stop animations from the previous status."""
    widget = RecordingTrafficLightWidget()
    engine = LightAnimationEngine(widget)
    engine.set_status(CodexStatus.WORKING)
    old_animation = engine._animations[0]

    engine.set_status(CodexStatus.IDLE)

    assert old_animation.state() == QAbstractAnimation.Stopped
    assert engine._animations == []
