"""Data models used by the Link Failover daemon."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    """Represent one configured failover link."""

    id: int
    iface: str
    priority: int


@dataclass(frozen=True)
class CheckResult:
    """Represent the outcome of one link health check."""

    link: Link
    healthy: bool
    latency_ms: float | None
    error: str | None
