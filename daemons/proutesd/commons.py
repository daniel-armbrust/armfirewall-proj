"""Shared helpers used by the policy routing executor."""

from __future__ import annotations

from typing import Any


def ip_family_arg(family: str) -> str:
    """Return the iproute2 family flag."""
    return "-6" if family.upper() == "IPV6" else "-4"


def normalized_ids(payload: dict[str, Any], key: str) -> list[int]:
    """Return a normalized list of integer ids from the payload."""
    values = payload.get(key)

    if not isinstance(values, list):
        return []
    
    return [int(value) for value in values]


def add_if_value(command: list[str], keyword: str, value: Any) -> None:
    """Append an iproute2 keyword and value when present."""
    
    if value is None:
        return
    
    text = str(value).strip()
    
    if text:
        command.extend([keyword, text])
