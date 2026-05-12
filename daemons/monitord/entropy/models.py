"""Data models used by the entropy monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntropyCounters:
    """Hold the available kernel entropy counter."""

    available: int = 0
