"""Data models used by the latency monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LatencyTarget:
    """Describe one latency monitoring target."""

    name: str
    address: str
    iface: str = ""
    description: str = ""
    packet_count: int = 3
    timeout_seconds: int = 3


@dataclass(frozen=True)
class PingResult:
    """Hold latency and packet loss values returned by ping."""

    min_ms: float | None
    avg_ms: float | None
    max_ms: float | None
    loss_pct: float
