#!/usr/bin/env python3
"""Filesystem monitoring collector based on Monitorix fs metrics."""

from __future__ import annotations

import os
import re
from pathlib import Path

from ..constants import RRD_DIR
from ..rrd import rrd_needs_creation, rrd_safe_name
from core import log as logger
from core.process import run_command

from .constants import (
    COLLECT_INTERVAL_SECONDS,
    LOG_SOURCE,
    PROC_DISKSTATS,
    PROC_MOUNTINFO,
    PSEUDO_FILESYSTEMS,
    RRD_DATA_SOURCES,
)
from .graphs import generate_graphs
from .models import DiskStats, FilesystemCounters, FilesystemSnapshot, MountInfo


class FilesystemMonitor:
    """Collect Linux filesystem metrics and maintain their RRD graphs."""

    name = "fs"
    interval_seconds = COLLECT_INTERVAL_SECONDS

    def __init__(self, rrdtool: str) -> None:
        """Prepare the filesystem monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one filesystem monitoring cycle."""
        snapshots = collect_filesystem_snapshots()
        
        for index, snapshot in enumerate(snapshots):
            rrd_path = update_rrd(self.rrdtool, snapshot)
            generate_graphs(self.rrdtool, snapshot, rrd_path, index)
        
        logger.info(f"Monitored {len(snapshots)} filesystem metrics into {RRD_DIR}.", source=LOG_SOURCE)


def decode_mount_field(value: str) -> str:
    """Decode octal escapes used by Linux mountinfo fields."""
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def sanitize_mount_name(mountpoint: str) -> str:
    """Return a filesystem-safe name for one mountpoint."""
    return rrd_safe_name(mountpoint)


def rrd_path_for_mount(mountpoint: str) -> Path:
    """Return the RRD path for one mounted filesystem."""
    return RRD_DIR / f"fs-{sanitize_mount_name(mountpoint)}.rrd"


def read_mounts() -> list[MountInfo]:
    """Read real mounted filesystems from /proc/self/mountinfo."""
    mounts: list[MountInfo] = []
    seen_mountpoints: set[str] = set()

    for line in PROC_MOUNTINFO.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if " - " not in line or "-" not in fields or len(fields) < 10:
            continue

        separator = fields.index("-")
        if separator + 2 >= len(fields):
            continue

        major_minor = fields[2].split(":", 1)
        if len(major_minor) != 2:
            continue

        mountpoint = decode_mount_field(fields[4])
        fstype = fields[separator + 1]
        source = decode_mount_field(fields[separator + 2])

        if fstype in PSEUDO_FILESYSTEMS or mountpoint in seen_mountpoints:
            continue

        if source.startswith(("proc", "sysfs", "tmpfs", "cgroup")):
            continue

        try:
            major = int(major_minor[0])
            minor = int(major_minor[1])
        except ValueError:
            continue

        mounts.append(MountInfo(mountpoint=mountpoint, fstype=fstype, source=source, major=major, minor=minor))
        seen_mountpoints.add(mountpoint)

    return sorted(mounts, key=lambda mount: (mount.mountpoint != "/", mount.mountpoint))


def read_diskstats() -> dict[tuple[int, int], DiskStats]:
    """Read Linux diskstats counters keyed by major and minor number."""
    stats: dict[tuple[int, int], DiskStats] = {}

    if not PROC_DISKSTATS.exists():
        return stats

    for line in PROC_DISKSTATS.read_text(encoding="utf-8").splitlines():
        fields = line.split()

        if len(fields) < 11:
            continue
        
        try:
            major = int(fields[0])
            minor = int(fields[1])
            stats[(major, minor)] = DiskStats(
                read_count=int(fields[3]),
                read_ms=int(fields[6]),
                write_count=int(fields[7]),
                write_ms=int(fields[10]),
            )
        except ValueError:
            continue

    return stats


def usage_percent(mountpoint: str) -> tuple[float, float]:
    """Calculate filesystem and inode usage percentages for one mountpoint."""
    stat = os.statvfs(mountpoint)
    block_total = stat.f_blocks
    block_free = stat.f_bfree
    inode_total = stat.f_files
    inode_free = stat.f_ffree

    used_pct = 0.0
    inode_pct = 0.0

    if block_total > 0:
        used_pct = ((block_total - block_free) * 100.0) / block_total
    
    if inode_total > 0:
        inode_pct = ((inode_total - inode_free) * 100.0) / inode_total
    
    return used_pct, inode_pct


def disk_activity(mount: MountInfo, diskstats: dict[tuple[int, int], DiskStats]) -> tuple[float, float]:
    """Return raw disk activity counters for one mountpoint device."""
    stats = diskstats.get((mount.major, mount.minor))
    
    if not stats:
        return 0.0, 0.0
    
    return float(stats.read_count + stats.write_count), float(stats.read_ms + stats.write_ms)


def collect_filesystem_snapshots() -> list[FilesystemSnapshot]:
    """Collect current filesystem usage and disk activity samples."""
    snapshots: list[FilesystemSnapshot] = []
    diskstats = read_diskstats()

    for mount in read_mounts():
        try:
            used_pct, inode_pct = usage_percent(mount.mountpoint)
            io_ops, io_time_ms = disk_activity(mount, diskstats)
        except OSError as exc:
            logger.error(f"Unable to collect filesystem {mount.mountpoint}: {exc}", source=LOG_SOURCE)
            continue

        snapshots.append(
            FilesystemSnapshot(
                mount=mount,
                counters=FilesystemCounters(
                    usage_pct=used_pct,
                    inode_pct=inode_pct,
                    io_ops=io_ops,
                    io_time_ms=io_time_ms,
                ),
            )
        )

    return snapshots


def ensure_rrd(rrdtool: str, mountpoint: str) -> Path:
    """Create one filesystem RRD file when it does not exist or has an old schema."""
    rrd_path = rrd_path_for_mount(mountpoint)
    
    if not rrd_needs_creation(rrdtool, rrd_path, RRD_DATA_SOURCES):
        return rrd_path

    heartbeat = max(COLLECT_INTERVAL_SECONDS * 3, 120)
    
    run_command(
        [
            rrdtool,
            "create",
            str(rrd_path),
            "--step",
            str(COLLECT_INTERVAL_SECONDS),
            f"DS:usage_pct:GAUGE:{heartbeat}:0:100",
            f"DS:inode_pct:GAUGE:{heartbeat}:0:100",
            f"DS:io_ops:DERIVE:{heartbeat}:0:U",
            f"DS:io_time_ms:DERIVE:{heartbeat}:0:U",
            "RRA:AVERAGE:0.5:1:8640",
            "RRA:AVERAGE:0.5:6:10080",
            "RRA:AVERAGE:0.5:30:1488",
            "RRA:MIN:0.5:1:8640",
            "RRA:MIN:0.5:6:10080",
            "RRA:MIN:0.5:30:1488",
            "RRA:MAX:0.5:1:8640",
            "RRA:MAX:0.5:6:10080",
            "RRA:MAX:0.5:30:1488",
            "RRA:LAST:0.5:1:8640",
            "RRA:LAST:0.5:6:10080",
            "RRA:LAST:0.5:30:1488",
        ]
    )
    logger.info(f"Created filesystem RRD file for {mountpoint}: {rrd_path}", source=LOG_SOURCE)
    
    return rrd_path


def update_rrd(rrdtool: str, snapshot: FilesystemSnapshot) -> Path:
    """Update one filesystem RRD with the latest collected counters."""
    rrd_path = ensure_rrd(rrdtool, snapshot.mount.mountpoint)
    counters = snapshot.counters
    
    update_value = (
        f"N:{counters.usage_pct:.6f}:{counters.inode_pct:.6f}:"
        f"{counters.io_ops:.0f}:{counters.io_time_ms:.0f}"
    )
    
    run_command([rrdtool, "update", str(rrd_path), update_value])
    
    return rrd_path