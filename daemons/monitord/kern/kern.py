#!/usr/bin/env python3
"""Kernel monitoring collector based on Monitorix kern.pm metrics."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..constants import COLLECT_INTERVAL_SECONDS, RRD_DIR, RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from core import log as logger

from .constants import (
    KERN_DS,
    LOG_SOURCE,
    MONITORIX_GRAPH_COLORS,
    PROC_DENTRY,
    PROC_FILE_NR,
    PROC_INODE_NR,
    PROC_STAT,
    RRD_PATH,
)
from .models import KernelCounters, KernelRawCounters


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


def safe_percent(used: int, total: int) -> float:
    """Return a percentage while avoiding division by zero."""
    if total <= 0:
        return 0.0
    return (used * 100.0) / total


def read_kernel_raw_counters() -> KernelRawCounters:
    """Read kernel CPU, context switch, and fork counters from /proc/stat."""
    raw = KernelRawCounters()
    cpu_values: list[int] | None = None
    context_switches: int | None = None
    forks: int | None = None

    try:
        for line in PROC_STAT.read_text(encoding="utf-8").splitlines():
            if line.startswith("cpu "):
                values = [int(value) for value in line.split()[1:10]]
                cpu_values = values + [0] * (9 - len(values))
                continue
            if line.startswith("ctxt "):
                context_switches = int(line.split()[1])
                continue
            if line.startswith("processes "):
                forks = int(line.split()[1])
                continue
    except (OSError, ValueError, IndexError):
        return raw

    if not cpu_values:
        return raw

    return KernelRawCounters(
        user=cpu_values[0],
        nice=cpu_values[1],
        sys=cpu_values[2],
        idle=cpu_values[3],
        iow=cpu_values[4],
        irq=cpu_values[5],
        sirq=cpu_values[6],
        steal=cpu_values[7],
        guest=cpu_values[8],
        context_switches=context_switches,
        forks=forks,
    )


def read_dentry_percent() -> float:
    """Read dentry usage percentage from /proc/sys/fs/dentry-state."""
    try:
        values = [int(value) for value in PROC_DENTRY.read_text(encoding="utf-8").split()[:2]]
        return safe_percent(values[0], values[0] + values[1])
    except (OSError, ValueError, IndexError):
        return 0.0


def read_file_percent() -> float:
    """Read file handle usage percentage from /proc/sys/fs/file-nr."""
    try:
        allocated, _, maximum = [int(value) for value in PROC_FILE_NR.read_text(encoding="utf-8").split()[:3]]
        return safe_percent(allocated, maximum)
    except (OSError, ValueError, IndexError):
        return 0.0


def read_inode_percent() -> float:
    """Read inode usage percentage from /proc/sys/fs/inode-nr."""
    try:
        allocated, free = [int(value) for value in PROC_INODE_NR.read_text(encoding="utf-8").split()[:2]]
        return safe_percent(allocated, allocated + free)
    except (OSError, ValueError, IndexError):
        return 0.0


def normalize_cpu_percent(current: KernelRawCounters, previous: KernelRawCounters | None) -> tuple[float | None, ...]:
    """Convert raw cumulative CPU jiffies into usage percentages."""
    if previous is None:
        return (None, None, None, None, None, None, None, None, None)

    current_values = [
        current.user,
        current.nice,
        current.sys,
        current.idle,
        current.iow,
        current.irq,
        current.sirq,
        current.steal,
        current.guest,
    ]
    previous_values = [
        previous.user,
        previous.nice,
        previous.sys,
        previous.idle,
        previous.iow,
        previous.irq,
        previous.sirq,
        previous.steal,
        previous.guest,
    ]
    if any(current_value < previous_value for current_value, previous_value in zip(current_values, previous_values)):
        return (None, None, None, None, None, None, None, None, None)

    deltas = [current_value - previous_value for current_value, previous_value in zip(current_values, previous_values)]
    total = sum(deltas)
    if total <= 0:
        return (None, None, None, None, None, None, None, None, None)

    return tuple((delta * 100.0) / total for delta in deltas)


def collect_kernel_counters(previous: KernelRawCounters | None) -> tuple[KernelCounters, KernelRawCounters]:
    """Collect one normalized kernel monitoring sample."""
    raw = read_kernel_raw_counters()
    cpu = normalize_cpu_percent(raw, previous)
    counters = KernelCounters(
        user=cpu[0],
        nice=cpu[1],
        sys=cpu[2],
        idle=cpu[3],
        iow=cpu[4],
        irq=cpu[5],
        sirq=cpu[6],
        steal=cpu[7],
        guest=cpu[8],
        context_switches=raw.context_switches,
        dentry=read_dentry_percent(),
        file=read_file_percent(),
        inode=read_inode_percent(),
        forks=raw.forks,
    )
    return counters, raw


def rrd_value(value: float | int | None) -> str:
    """Convert Python values into RRD update fields."""
    if value is None:
        return "U"
    return str(value)


def ensure_rrd(rrdtool: str) -> None:
    """Create the kernel RRD file when needed."""
    if RRD_PATH.exists() and rrd_data_sources(rrdtool, RRD_PATH) != set(KERN_DS):
        RRD_PATH.unlink()

    if RRD_PATH.exists():
        return

    heartbeat = max(COLLECT_INTERVAL_SECONDS * 3, 120)
    run_command(
        [
            rrdtool,
            "create",
            str(RRD_PATH),
            "--step",
            str(COLLECT_INTERVAL_SECONDS),
            f"DS:kern_user:GAUGE:{heartbeat}:0:100",
            f"DS:kern_nice:GAUGE:{heartbeat}:0:100",
            f"DS:kern_sys:GAUGE:{heartbeat}:0:100",
            f"DS:kern_idle:GAUGE:{heartbeat}:0:100",
            f"DS:kern_iow:GAUGE:{heartbeat}:0:100",
            f"DS:kern_irq:GAUGE:{heartbeat}:0:100",
            f"DS:kern_sirq:GAUGE:{heartbeat}:0:100",
            f"DS:kern_steal:GAUGE:{heartbeat}:0:100",
            f"DS:kern_guest:GAUGE:{heartbeat}:0:100",
            f"DS:kern_cs:COUNTER:{heartbeat}:0:U",
            f"DS:kern_dentry:GAUGE:{heartbeat}:0:100",
            f"DS:kern_file:GAUGE:{heartbeat}:0:100",
            f"DS:kern_inode:GAUGE:{heartbeat}:0:100",
            f"DS:kern_forks:COUNTER:{heartbeat}:0:U",
            f"DS:kern_vforks:COUNTER:{heartbeat}:0:U",
            f"DS:kern_val03:GAUGE:{heartbeat}:0:100",
            f"DS:kern_val04:GAUGE:{heartbeat}:0:100",
            f"DS:kern_val05:GAUGE:{heartbeat}:0:100",
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
    logger.info(f"Created kernel RRD file: {RRD_PATH}", source=LOG_SOURCE)


def update_rrd(rrdtool: str, counters: KernelCounters) -> None:
    """Update the kernel RRD with the latest raw counters."""
    ensure_rrd(rrdtool)
    values = [
        counters.user,
        counters.nice,
        counters.sys,
        counters.idle,
        counters.iow,
        counters.irq,
        counters.sirq,
        counters.steal,
        counters.guest,
        counters.context_switches,
        counters.dentry,
        counters.file,
        counters.inode,
        counters.forks,
        counters.vforks,
        counters.val03,
        counters.val04,
        counters.val05,
    ]
    update_value = "N:" + ":".join(rrd_value(value) for value in values)
    run_command([rrdtool, "update", str(RRD_PATH), update_value])


def graph_cpu(rrdtool: str) -> None:
    """Generate kernel CPU usage graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "kern-cpu.png"
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
                f"Kernel usage - {period_label}",
                "--vertical-label",
                "Stacked Percent (%)",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:user={RRD_PATH}:kern_user:AVERAGE",
                f"DEF:nice={RRD_PATH}:kern_nice:AVERAGE",
                f"DEF:sys={RRD_PATH}:kern_sys:AVERAGE",
                f"DEF:iow={RRD_PATH}:kern_iow:AVERAGE",
                f"DEF:irq={RRD_PATH}:kern_irq:AVERAGE",
                f"DEF:sirq={RRD_PATH}:kern_sirq:AVERAGE",
                f"DEF:steal={RRD_PATH}:kern_steal:AVERAGE",
                f"DEF:guest={RRD_PATH}:kern_guest:AVERAGE",
                "CDEF:s_nice=user,nice,+",
                "CDEF:s_sys=s_nice,sys,+",
                "CDEF:s_iow=s_sys,iow,+",
                "CDEF:s_irq=s_iow,irq,+",
                "CDEF:s_sirq=s_irq,sirq,+",
                "CDEF:s_steal=s_sirq,steal,+",
                "CDEF:s_guest=s_steal,guest,+",
                "AREA:s_guest#448844:guest",
                "GPRINT:guest:LAST:     Current\\: %4.1lf%%",
                "GPRINT:guest:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:guest:MIN:    Min\\: %4.1lf%%",
                "GPRINT:guest:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_steal#44EE44:steal",
                "GPRINT:steal:LAST:     Current\\: %4.1lf%%",
                "GPRINT:steal:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:steal:MIN:    Min\\: %4.1lf%%",
                "GPRINT:steal:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_sirq#E29136:softIRQ",
                "GPRINT:sirq:LAST:   Current\\: %4.1lf%%",
                "GPRINT:sirq:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:sirq:MIN:    Min\\: %4.1lf%%",
                "GPRINT:sirq:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_irq#888888:IRQ",
                "GPRINT:irq:LAST:       Current\\: %4.1lf%%",
                "GPRINT:irq:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:irq:MIN:    Min\\: %4.1lf%%",
                "GPRINT:irq:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_iow#EE44EE:I/O wait",
                "GPRINT:iow:LAST:  Current\\: %4.1lf%%",
                "GPRINT:iow:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:iow:MIN:    Min\\: %4.1lf%%",
                "GPRINT:iow:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_sys#44EEEE:system",
                "GPRINT:sys:LAST:    Current\\: %4.1lf%%",
                "GPRINT:sys:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:sys:MIN:    Min\\: %4.1lf%%",
                "GPRINT:sys:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_nice#EEEE44:nice",
                "GPRINT:nice:LAST:      Current\\: %4.1lf%%",
                "GPRINT:nice:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:nice:MIN:    Min\\: %4.1lf%%",
                "GPRINT:nice:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:user#4444EE:user",
                "GPRINT:user:LAST:      Current\\: %4.1lf%%",
                "GPRINT:user:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:user:MIN:    Min\\: %4.1lf%%",
                "GPRINT:user:MAX:    Max\\: %4.1lf%%\\n",
                "LINE1:s_guest#1F881F",
                "LINE1:s_steal#00EE00",
                "LINE1:s_sirq#D86612",
                "LINE1:s_irq#CCCCCC",
                "LINE1:s_iow#EE00EE",
                "LINE1:s_sys#00EEEE",
                "LINE1:s_nice#EEEE00",
                "LINE1:user#0000EE",
            ]
        )


def graph_context(rrdtool: str) -> None:
    """Generate context switches and forks graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "kern-context.png"
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
                f"Context switches and forks - {period_label}",
                "--vertical-label",
                "CS & forks/s",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:cs={RRD_PATH}:kern_cs:AVERAGE",
                f"DEF:forks={RRD_PATH}:kern_forks:AVERAGE",
                "AREA:cs#44AAEE:Context switches",
                "GPRINT:cs:LAST:     Current\\: %6.0lf\\n",
                "AREA:forks#4444EE:Forks",
                "GPRINT:forks:LAST:                Current\\: %6.0lf\\n",
                "LINE1:cs#00EEEE",
                "LINE1:forks#0000EE",
            ]
        )


def graph_kernel_usage(rrdtool: str) -> None:
    """Generate dentry, file, and inode usage graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "kern-usage.png"
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
                f"Kernel usage - {period_label}",
                "--vertical-label",
                "Percent (%)",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:dentry={RRD_PATH}:kern_dentry:AVERAGE",
                f"DEF:file={RRD_PATH}:kern_file:AVERAGE",
                f"DEF:inode={RRD_PATH}:kern_inode:AVERAGE",
                "AREA:inode#4444EE:inode",
                "GPRINT:inode:LAST:                Current\\:  %4.1lf%%\\n",
                "AREA:dentry#EEEE44:dentry",
                "GPRINT:dentry:LAST:               Current\\:  %4.1lf%%\\n",
                "AREA:file#EE44EE:file",
                "GPRINT:file:LAST:                 Current\\:  %4.1lf%%\\n",
                "LINE2:inode#0000EE",
                "LINE2:dentry#EEEE00",
                "LINE2:file#EE00EE",
            ]
        )


def generate_graphs(rrdtool: str) -> None:
    """Generate all kernel graph images."""
    graph_cpu(rrdtool)
    graph_context(rrdtool)
    graph_kernel_usage(rrdtool)


class KernelMonitor:
    """Collect Linux kernel metrics and maintain their RRD graphs."""

    name = "kern"

    def __init__(self, rrdtool: str) -> None:
        """Prepare the kernel monitor dependencies."""
        self.rrdtool = rrdtool
        self.previous_raw: KernelRawCounters | None = None

    def collect(self) -> None:
        """Run one kernel monitoring cycle."""
        counters, raw = collect_kernel_counters(self.previous_raw)
        update_rrd(self.rrdtool, counters)
        generate_graphs(self.rrdtool)
        self.previous_raw = raw
        logger.info(f"Monitored kernel metrics into {RRD_DIR}.", source=LOG_SOURCE)
