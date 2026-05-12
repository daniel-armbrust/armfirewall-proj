"""Data models used by the interface monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InterfaceCounters:
    """Hold raw counters collected from /proc/net/dev."""

    rx_bytes: int = 0
    rx_packets: int = 0
    rx_errors: int = 0
    rx_dropped: int = 0
    tx_bytes: int = 0
    tx_packets: int = 0
    tx_errors: int = 0
    tx_dropped: int = 0


@dataclass(frozen=True)
class CounterSnapshot:
    """Hold one timestamped interface counter sample."""

    timestamp: float
    counters: InterfaceCounters
