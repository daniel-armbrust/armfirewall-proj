"""Data models used by the filesystem monitoring collector."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MountInfo:
    """Describe one mounted filesystem from Linux mountinfo."""

    mountpoint: str
    fstype: str
    source: str
    major: int
    minor: int


@dataclass(frozen=True)
class DiskStats:
    """Hold raw Linux diskstats counters used by Monitorix fs graphs."""

    read_count: int = 0
    write_count: int = 0
    read_ms: int = 0
    write_ms: int = 0


@dataclass(frozen=True)
class FilesystemCounters:
    """Hold filesystem usage and disk activity counters."""

    usage_pct: float = 0.0
    inode_pct: float = 0.0
    io_ops: float = 0.0
    io_time_ms: float = 0.0


@dataclass(frozen=True)
class FilesystemSnapshot:
    """Hold one filesystem sample prepared for RRD update."""

    mount: MountInfo
    counters: FilesystemCounters
