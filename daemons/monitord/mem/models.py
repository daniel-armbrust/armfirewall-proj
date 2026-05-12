"""Data models used by the memory monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryCounters:
    """Hold Linux memory counters in KiB."""

    total: int = 0
    buffers: int = 0
    cached: int = 0
    free: int = 0
    active: int = 0
    inactive: int = 0
