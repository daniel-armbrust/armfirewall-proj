"""Filesystem graph generation helpers."""

from __future__ import annotations

from pathlib import Path

from core.process import run_command

from ..constants import RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from ..rrd import rrd_label, rrd_safe_name
from .constants import MONITORIX_FS_LINE_COLORS, MONITORIX_GRAPH_COLORS
from .models import FilesystemSnapshot


def image_path_for_mount(mountpoint: str, suffix: str) -> Path:
    """Return one graph image path for a mounted filesystem."""
    return RRD_IMG_DIR / f"fs-{rrd_safe_name(mountpoint)}-{suffix}.png"


def line_color_for_mount(mountpoint: str, index: int) -> str:
    """Return the Monitorix-style color used for one filesystem."""
    if mountpoint == "/":
        return "#EE4444"
    
    if mountpoint == "swap":
        return "#CCCCCC"
    
    if mountpoint == "/boot":
        return "#666666"
    
    return MONITORIX_FS_LINE_COLORS[index % len(MONITORIX_FS_LINE_COLORS)]


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
