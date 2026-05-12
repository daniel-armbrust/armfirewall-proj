"""Data models used by the load average monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadAvgCounters:
    """Hold Linux load average counters."""

    load1: float = 0.0
    load5: float = 0.0
    load15: float = 0.0
