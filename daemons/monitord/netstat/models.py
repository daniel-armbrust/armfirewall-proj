"""Data models used by the socket state monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FamilySocketCounters:
    """Hold TCP state and UDP socket counts for one address family."""

    closed: int = 0
    listen: int = 0
    synsent: int = 0
    synrecv: int = 0
    estblshd: int = 0
    finwait1: int = 0
    finwait2: int = 0
    closing: int = 0
    timewait: int = 0
    closewait: int = 0
    lastack: int = 0
    unknown: int = 0
    udp: int = 0
    val1: int = 0
    val2: int = 0
    val3: int = 0
    val4: int = 0
    val5: int = 0


@dataclass
class SocketCounters:
    """Hold IPv4 and IPv6 socket counters."""

    ipv4: FamilySocketCounters
    ipv6: FamilySocketCounters
