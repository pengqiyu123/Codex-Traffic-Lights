"""Task 12 startup integration and LED contrast tests."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from codex_traffic_lights.animation.effects import (
    INTERMITTENT_BLINK_EFFECT,
    OFF_EFFECT,
    SLOW_FLASH_EFFECT,
)
from codex_traffic_lights.hook_installer import HookInstaller


class FakeSignal:
    """Small callback signal for entrypoint wiring tests."""

    def __init__(self) -> None:
        """Create an empty fake signal."""
        self.connected_slot: Any | None = None

    def connect(self, slot: Any) -> None:
        """Record a connected slot."""
        self.connected_slot = slot

    def emit(self, value: bool) -> None:
        """Invoke the connected slot with a boolean value."""
        if self.connected_slot is not None:
            self.connected_slot(value)


def test_task12_led_contrast_values_are_more_visible() -> None:
    """OFF should be darker, while alerting effects should peak brighter."""
    assert OFF_EFFECT.min_opacity < 0.05
    assert OFF_EFFECT.max_opacity < 0.08
    assert INTERMITTENT_BLINK_EFFECT.max_opacity >= 0.75
    assert SLOW_FLASH_EFFECT.max_opacity >= 0.75


def test_task12_hook_install_success_calls_both_installers(capsys: Any) -> None:
    """Startup hook install should invoke Codex and Claude installers."""
    entry = importlib.import_module("codex_traffic_lights.__main__")
    calls: list[str] = []

    class FakeInstaller:
        def install_codex_hooks(self) -> None:
            calls.append("codex")

        def install_claude_hooks(self) -> None:
            calls.append("claude")

    entry._install_hooks(FakeInstaller())

    assert calls == ["codex", "claude"]
    assert "Hooks installed successfully" in capsys.readouterr().out


def test_task12_real_hook_installer_mocked_write(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Real HookInstaller methods should run with mocked file writes."""
    written_paths: list[Path] = []

    def fake_write(_self: HookInstaller, path: Path, _data: dict[str, Any]) -> None:
        written_paths.append(path)

    monkeypatch.setattr(HookInstaller, "_write_with_backup", fake_write)

    installer = HookInstaller(home=tmp_path, python_executable="python")
    installer.install_codex_hooks()
    installer.install_claude_hooks()

    assert written_paths == [
        tmp_path / ".codex" / "hooks.json",
        tmp_path / ".claude" / "settings.json",
    ]


def test_task12_hook_install_failure_is_non_fatal(capsys: Any) -> None:
    """Hook install failures should be logged and should not stop startup."""
    entry = importlib.import_module("codex_traffic_lights.__main__")

    class FailingInstaller:
        def install_codex_hooks(self) -> None:
            raise RuntimeError("disk locked")

        def install_claude_hooks(self) -> None:
            raise AssertionError("should not reach after codex failure")

    entry._install_hooks(FailingInstaller())

    assert "Hook install failed (non-fatal): disk locked" in capsys.readouterr().out


def test_task12_power_button_hides_and_restores_window() -> None:
    """Power toggle should minimize to tray and restore on second toggle."""
    entry = importlib.import_module("codex_traffic_lights.__main__")

    class FakeSideButtons:
        def __init__(self) -> None:
            self.power_toggled = FakeSignal()

    class FakeWindow:
        def __init__(self) -> None:
            self.side_buttons = FakeSideButtons()
            self.hidden = False
            self.shown = False
            self.raised = False
            self.activated = False

        def hide(self) -> None:
            self.hidden = True

        def show(self) -> None:
            self.shown = True

        def raise_(self) -> None:
            self.raised = True

        def activateWindow(self) -> None:  # noqa: N802
            self.activated = True

    class FakeTray:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def show_message(self, title: str, text: str) -> None:
            self.messages.append((title, text))

    window = FakeWindow()
    tray = FakeTray()

    entry._connect_power_button(window, tray)
    window.side_buttons.power_toggled.emit(True)
    window.side_buttons.power_toggled.emit(False)

    assert window.hidden is True
    assert tray.messages == [("Codex Traffic Lights", "已最小化到托盘，双击图标恢复")]
    assert window.shown is True
    assert window.raised is True
    assert window.activated is True
