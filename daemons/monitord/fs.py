#!/usr/bin/env python3
"""Filesystem monitoring collector based on Monitorix fs metrics."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import log as logger
from periods import GRAPH_PERIODS, period_image_path


LOG_SOURCE = "monitord/fs.py"
COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFW_MONITORD_INTERVAL", "10"))
RRD_DIR = ROOT_DIR / "rrd"
RRD_IMG_DIR = RRD_DIR / "img"
PROC_MOUNTINFO = Path("/proc/self/mountinfo")
PROC_DISKSTATS = Path("/proc/diskstats")
RRD_DATA_SOURCES = {"usage_pct", "inode_pct", "io_ops", "io_time_ms"}
PSEUDO_FILESYSTEMS = {
    "autofs",
    "binfmt_misc",
    "bpf",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devpts",
    "devtmpfs",
    "efivarfs",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "proc",
    "pstore",
    "rpc_pipefs",
    "securityfs",
    "selinuxfs",
    "sysfs",
    "tmpfs",
    "tracefs",
}
MONITORIX_GRAPH_COLORS = [
    "--color=CANVAS#000000",
    "--color=BACK#101010",
    "--color=FONT#C0C0C0",
    "--color=MGRID#80C080",
    "--color=GRID#808020",
    "--color=FRAME#808080",
    "--color=ARROW#FFFFFF",
    "--color=SHADEA#404040",
    "--color=SHADEB#404040",
    "--color=AXIS#101010",
]
MONITORIX_FS_LINE_COLORS = [
    "#FFA500",
    "#44EEEE",
    "#44EE44",
    "#4444EE",
    "#448844",
    "#5F04B4",
    "#EE44EE",
    "#EEEE44",
]


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


def run_command(command: list[str]) -> None:
    """Run one external command and raise a useful error on failure."""
    subprocess.run(command, check=True, text=True, capture_output=True)


def rrd_data_sources(rrdtool: str, rrd_path: Path) -> set[str]:
    """Return the data source names currently stored in an RRD file."""
    result = subprocess.run([rrdtool, "info", str(rrd_path)], check=True, text=True, capture_output=True)
    sources: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("ds["):
            continue
        sources.add(line.split("[", 1)[1].split("]", 1)[0])
    return sources


def decode_mount_field(value: str) -> str:
    """Decode octal escapes used by Linux mountinfo fields."""
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def sanitize_mount_name(mountpoint: str) -> str:
    """Return a filesystem-safe name for one mountpoint."""
    if mountpoint == "/":
        return "root"
    sanitized = mountpoint.strip("/").replace("/", "_")
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", sanitized)
    return sanitized or "unknown"


def rrd_label(value: str) -> str:
    """Escape one value for use as an RRD graph label."""
    return value.replace("\\", "\\\\").replace(":", "\\:")


def line_color_for_mount(mountpoint: str, index: int) -> str:
    """Return the Monitorix-style color used for one filesystem."""
    if mountpoint == "/":
        return "#EE4444"
    if mountpoint == "swap":
        return "#CCCCCC"
    if mountpoint == "/boot":
        return "#666666"
    return MONITORIX_FS_LINE_COLORS[index % len(MONITORIX_FS_LINE_COLORS)]


def rrd_path_for_mount(mountpoint: str) -> Path:
    """Return the RRD path for one mounted filesystem."""
    return RRD_DIR / f"fs-{sanitize_mount_name(mountpoint)}.rrd"


def image_path_for_mount(mountpoint: str, suffix: str) -> Path:
    """Return one graph image path for a mounted filesystem."""
    return RRD_IMG_DIR / f"fs-{sanitize_mount_name(mountpoint)}-{suffix}.png"


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
    if rrd_path.exists() and rrd_data_sources(rrdtool, rrd_path) != RRD_DATA_SOURCES:
        rrd_path.unlink()

    if rrd_path.exists():
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


def graph_usage(rrdtool: str, snapshot: FilesystemSnapshot, rrd_path: Path, color: str) -> None:
    """Generate filesystem usage graphs for all standard periods."""
    base_path = image_path_for_mount(snapshot.mount.mountpoint, "usage")
    label = rrd_label(snapshot.mount.mountpoint)
    for period_name, period_label, period_start in GRAPH_PERIODS:
        run_command(
            [
                rrdtool,
                "graph",
                str(period_image_path(base_path, period_name)),
                "--imgformat",
                "PNG",
                "--start",
                period_start,
                "--width",
                "800",
                "--height",
                "300",
                "--title",
                f"{snapshot.mount.mountpoint} filesystem usage - {period_label}",
                "--vertical-label",
                "Percent (%)",
                "--upper-limit",
                "100",
                "--lower-limit",
                "0",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:usage={rrd_path}:usage_pct:AVERAGE",
                f"AREA:usage{color}:{label}",
                "GPRINT:usage:LAST: Cur\\: %4.1lf%%",
                "GPRINT:usage:MIN: Min\\: %4.1lf%%",
                "GPRINT:usage:MAX: Max\\: %4.1lf%%\\n",
                f"LINE2:usage{color}",
            ]
        )


def graph_inodes(rrdtool: str, snapshot: FilesystemSnapshot, rrd_path: Path, color: str) -> None:
    """Generate inode usage graphs for all standard periods."""
    base_path = image_path_for_mount(snapshot.mount.mountpoint, "inodes")
    label = rrd_label(snapshot.mount.mountpoint)
    for period_name, period_label, period_start in GRAPH_PERIODS:
        run_command(
            [
                rrdtool,
                "graph",
                str(period_image_path(base_path, period_name)),
                "--imgformat",
                "PNG",
                "--start",
                period_start,
                "--width",
                "800",
                "--height",
                "300",
                "--title",
                f"{snapshot.mount.mountpoint} inode usage - {period_label}",
                "--vertical-label",
                "Percent (%)",
                "--upper-limit",
                "100",
                "--lower-limit",
                "0",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:inodes={rrd_path}:inode_pct:AVERAGE",
                f"AREA:inodes{color}:{label}",
                "GPRINT:inodes:LAST: Cur\\: %4.1lf%%",
                "GPRINT:inodes:MIN: Min\\: %4.1lf%%",
                "GPRINT:inodes:MAX: Max\\: %4.1lf%%\\n",
                f"LINE2:inodes{color}",
            ]
        )


def graph_io_ops(rrdtool: str, snapshot: FilesystemSnapshot, rrd_path: Path, color: str) -> None:
    """Generate disk I/O operation graphs for all standard periods."""
    base_path = image_path_for_mount(snapshot.mount.mountpoint, "io-ops")
    label = rrd_label(snapshot.mount.mountpoint)
    for period_name, period_label, period_start in GRAPH_PERIODS:
        run_command(
            [
                rrdtool,
                "graph",
                str(period_image_path(base_path, period_name)),
                "--imgformat",
                "PNG",
                "--start",
                period_start,
                "--width",
                "800",
                "--height",
                "300",
                "--title",
                f"{snapshot.mount.mountpoint} I/O activity - {period_label}",
                "--vertical-label",
                "Reads+Writes/s",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:io_ops={rrd_path}:io_ops:AVERAGE",
                f"LINE2:io_ops{color}:{label}",
                "GPRINT:io_ops:LAST: Cur\\: %4.0lf",
                "GPRINT:io_ops:MIN: Min\\: %4.0lf",
                "GPRINT:io_ops:MAX: Max\\: %4.0lf\\n",
            ]
        )


def graph_io_time(rrdtool: str, snapshot: FilesystemSnapshot, rrd_path: Path, color: str) -> None:
    """Generate disk I/O time graphs for all standard periods."""
    base_path = image_path_for_mount(snapshot.mount.mountpoint, "io-time")
    label = rrd_label(snapshot.mount.mountpoint)
    for period_name, period_label, period_start in GRAPH_PERIODS:
        run_command(
            [
                rrdtool,
                "graph",
                str(period_image_path(base_path, period_name)),
                "--imgformat",
                "PNG",
                "--start",
                period_start,
                "--width",
                "800",
                "--height",
                "300",
                "--title",
                f"{snapshot.mount.mountpoint} I/O time - {period_label}",
                "--vertical-label",
                "Milliseconds/s",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:io_time={rrd_path}:io_time_ms:AVERAGE",
                f"LINE2:io_time{color}:{label}",
                "GPRINT:io_time:LAST: Cur\\: %4.1lf",
                "GPRINT:io_time:MIN: Min\\: %4.1lf",
                "GPRINT:io_time:MAX: Max\\: %4.1lf\\n",
            ]
        )


def generate_graphs(rrdtool: str, snapshot: FilesystemSnapshot, rrd_path: Path, index: int) -> None:
    """Generate all filesystem graph images for one mounted filesystem."""
    color = line_color_for_mount(snapshot.mount.mountpoint, index)
    graph_usage(rrdtool, snapshot, rrd_path, color)
    graph_inodes(rrdtool, snapshot, rrd_path, color)
    graph_io_ops(rrdtool, snapshot, rrd_path, color)
    graph_io_time(rrdtool, snapshot, rrd_path, color)


class FilesystemMonitor:
    """Collect Linux filesystem metrics and maintain their RRD graphs."""

    name = "fs"

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
