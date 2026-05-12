"""Shared helpers for ArmFirewall work request executors."""

from __future__ import annotations

import json
from typing import Any


def decode_payload(payload_json: str | None) -> dict[str, Any]:
    """Decode a work request JSON payload into a dictionary."""
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Payload JSON must decode to an object.")
    return payload
