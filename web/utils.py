"""Shared helpers for the ArmFirewall Web layer."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any


def decode_payload(payload_json: str | None) -> dict[str, Any]:
    """Decode a JSON payload into a dictionary."""
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Payload JSON must decode to an object.")
    return payload


def safe_decode_payload(payload_json: str | None) -> dict[str, Any]:
    """Decode a JSON payload, returning an empty dictionary on invalid JSON."""
    try:
        return decode_payload(payload_json)
    except RuntimeError:
        return {}


def summarize_statuses(rows: Sequence[dict[str, Any]], statuses: Sequence[str]) -> dict[str, int]:
    """Return a total and per-status summary for Web API rows."""
    summary = {"total": len(rows)}
    summary.update({status: 0 for status in statuses})

    for row in rows:
        status = str(row.get("status") or "")

        if status in summary:
            summary[status] += 1

    return summary
