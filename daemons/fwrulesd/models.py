"""Data models used by the firewall rule work request executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FirewallWorkRequest:
    """Hold one decoded firewall work request context."""

    work_request_id: str
    request_uid: str
    category_name: str
    category: str
    family: str
    target_name: str
    action_name: str
    target_rule_id: str
    payload: dict[str, Any]
