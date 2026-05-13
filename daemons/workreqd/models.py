"""Data models used by the work request daemon."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueuedWorkRequest:
    """Work request row ready to be dispatched."""

    id: int
    request_uid: str
    category_name: str
    action_name: str
    target_rule_id: str | None
    payload_json: str
    category: str
    family: str
    target_name: str
    script_name: str

    @classmethod
    def from_row(cls, row: Any) -> "QueuedWorkRequest":
        """Build a queued work request model from a SQLite row."""
        return cls(
            id=int(row["id"]),
            request_uid=str(row["request_uid"]),
            category_name=str(row["category_name"]),
            action_name=str(row["action_name"]),
            target_rule_id=None if row["target_rule_id"] is None else str(row["target_rule_id"]),
            payload_json=str(row["payload_json"]),
            category=str(row["category"]),
            family=str(row["family"]),
            target_name=str(row["target_name"]),
            script_name=str(row["script_name"]),
        )
