"""Data models used by the process status monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessCounters:
    """Hold Linux process state counters."""

    total: int = 0
    sleeping: int = 0
    running: int = 0
    wait_io: int = 0
    zombie: int = 0
    stopped: int = 0
    paging: int = 0
