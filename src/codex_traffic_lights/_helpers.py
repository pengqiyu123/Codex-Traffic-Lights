"""Small pure-Python helper functions shared across modules."""

from __future__ import annotations

from collections.abc import Mapping


def extract_string(mapping: Mapping[str, object], *keys: str) -> str | None:
    """Extract the first non-empty string value from a mapping."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def path_basename(value: str) -> str:
    """Extract a basename from POSIX or Windows-looking paths."""
    normalized = value.replace("\\", "/").rstrip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]
