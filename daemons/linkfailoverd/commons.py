"""Shared helpers used by the Link Failover daemon."""

from __future__ import annotations

from .constants import PING_TIME_RE


def parse_latency(output: str) -> float | None:
    """Extract ping latency in milliseconds from command output."""
    match = PING_TIME_RE.search(output)

    if not match:
        return None
    
    return float(match.group(1))
