"""PyInstaller build script for Codex Traffic Lights."""

from __future__ import annotations

import subprocess
from pathlib import Path

ADD_DATA = "src/codex_traffic_lights/resources;codex_traffic_lights/resources"
ICON = "src/codex_traffic_lights/resources/icons/app.ico"
ENTRYPOINT = "src/codex_traffic_lights/__main__.py"


def build_command() -> list[str]:
    """Return the PyInstaller command for the Windows desktop executable."""
    return [
        "pyinstaller",
        "--onefile",
        "--windowed",
        "--name",
        "codex-traffic-lights",
        "--add-data",
        ADD_DATA,
        "--icon",
        ICON,
        ENTRYPOINT,
    ]


def main() -> int:
    """Run PyInstaller and return its process exit code."""
    _validate_resources()
    completed = subprocess.run(build_command(), check=False)
    return completed.returncode


def _validate_resources() -> None:
    """Fail early if the configured resource paths are missing."""
    missing = [
        path
        for path in [
            Path("src/codex_traffic_lights/resources"),
            Path(ICON),
            Path(ENTRYPOINT),
        ]
        if not path.exists()
    ]
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing PyInstaller resource path(s): {formatted}")


if __name__ == "__main__":
    raise SystemExit(main())
