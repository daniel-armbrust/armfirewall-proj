"""Data models used by the kernel monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KernelRawCounters:
    """Hold raw Linux kernel counters read from procfs."""

    user: int = 0
    nice: int = 0
    sys: int = 0
    idle: int = 0
    iow: int = 0
    irq: int = 0
    sirq: int = 0
    steal: int = 0
    guest: int = 0
    context_switches: int | None = None
    forks: int | None = None


@dataclass(frozen=True)
class KernelCounters:
    """Hold normalized kernel metrics ready for RRD update."""

    user: float | None = None
    nice: float | None = None
    sys: float | None = None
    idle: float | None = None
    iow: float | None = None
    irq: float | None = None
    sirq: float | None = None
    steal: float | None = None
    guest: float | None = None
    context_switches: int | None = None
    dentry: float = 0.0
    file: float = 0.0
    inode: float = 0.0
    forks: int | None = None
    vforks: int = 0
    val03: int = 0
    val04: int = 0
    val05: int = 0
