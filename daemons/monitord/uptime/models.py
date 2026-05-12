"""Data models used by the uptime monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UptimeCounters:
    """Hold Linux uptime counters in seconds."""

    seconds: int = 0
