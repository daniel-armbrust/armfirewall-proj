#!/usr/bin/env python3
"""Memory monitoring collector based on Monitorix memory metrics."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import log as logger
from periods import GRAPH_PERIODS, period_image_path


LOG_SOURCE = "monitord/mem.py"
COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFW_MONITORD_INTERVAL", "10"))
RRD_DIR = ROOT_DIR / "rrd"
RRD_IMG_DIR = RRD_DIR / "img"
RRD_PATH = RRD_DIR / "mem.rrd"
PROC_MEMINFO = Path("/proc/meminfo")
MEMORY_DS = [
    "mem_total",
    "mem_buffers",
    "mem_cached",
    "mem_free",
    "mem_active",
    "mem_inactive",
]
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


@dataclass(frozen=True)
class MemoryCounters:
    """Hold Linux memory counters in KiB."""

    total: int = 0
    buffers: int = 0
    cached: int = 0
    free: int = 0
    active: int = 0
    inactive: int = 0


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


def read_memory_counters() -> MemoryCounters:
    """Read Linux memory counters from /proc/meminfo."""
    values: dict[str, int] = {}
    for line in PROC_MEMINFO.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0])

    free = values.get("MemFree", 0)
    free += values.get("SReclaimable", 0)
    free += values.get("SUnreclaim", 0)

    return MemoryCounters(
        total=values.get("MemTotal", 0),
        buffers=values.get("Buffers", 0),
        cached=values.get("Cached", 0),
        free=free,
        active=values.get("Active", 0),
        inactive=values.get("Inactive", 0),
    )


def ensure_rrd(rrdtool: str) -> None:
    """Create the memory RRD file when it does not exist or has an old schema."""
    if RRD_PATH.exists() and rrd_data_sources(rrdtool, RRD_PATH) != set(MEMORY_DS):
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
            f"DS:mem_total:GAUGE:{heartbeat}:0:U",
            f"DS:mem_buffers:GAUGE:{heartbeat}:0:U",
            f"DS:mem_cached:GAUGE:{heartbeat}:0:U",
            f"DS:mem_free:GAUGE:{heartbeat}:0:U",
            f"DS:mem_active:GAUGE:{heartbeat}:0:U",
            f"DS:mem_inactive:GAUGE:{heartbeat}:0:U",
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
    logger.info(f"Created memory RRD file: {RRD_PATH}", source=LOG_SOURCE)


def update_rrd(rrdtool: str, counters: MemoryCounters) -> None:
    """Update the memory RRD with the latest raw counters."""
    ensure_rrd(rrdtool)
    values = [
        counters.total,
        counters.buffers,
        counters.cached,
        counters.free,
        counters.active,
        counters.inactive,
    ]
    update_value = "N:" + ":".join(str(value) for value in values)
    run_command([rrdtool, "update", str(RRD_PATH), update_value])


def graph_memory(rrdtool: str) -> None:
    """Generate memory graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "mem-memory.png"
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
                f"Memory usage - {period_label}",
                "--vertical-label",
                "bytes",
                "--base",
                "1024",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:mtotl={RRD_PATH}:mem_total:AVERAGE",
                f"DEF:mbuff={RRD_PATH}:mem_buffers:AVERAGE",
                f"DEF:mcach={RRD_PATH}:mem_cached:AVERAGE",
                f"DEF:mfree={RRD_PATH}:mem_free:AVERAGE",
                f"DEF:macti={RRD_PATH}:mem_active:AVERAGE",
                f"DEF:minac={RRD_PATH}:mem_inactive:AVERAGE",
                "CDEF:m_mtotl=mtotl,1024,*",
                "CDEF:m_mbuff=mbuff,1024,*",
                "CDEF:m_mcach=mcach,1024,*",
                "CDEF:m_mused=m_mtotl,mfree,1024,*,-,m_mbuff,-,m_mcach,-",
                "CDEF:m_macti=macti,1024,*",
                "CDEF:m_minac=minac,1024,*",
                "AREA:m_mused#EE4444:Used",
                "AREA:m_mcach#44EE44:Cached",
                "AREA:m_mbuff#CCCCCC:Buffers",
                "AREA:m_macti#E29136:Active",
                "AREA:m_minac#448844:Inactive",
                "LINE2:m_minac#008800",
                "LINE2:m_macti#E29136",
                "LINE2:m_mbuff#CCCCCC",
                "LINE2:m_mcach#00EE00",
                "LINE2:m_mused#EE0000",
            ]
        )


class MemoryMonitor:
    """Collect Linux memory metrics and maintain their RRD graph."""

    name = "mem"

    def __init__(self, rrdtool: str) -> None:
        """Prepare the memory monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one memory monitoring cycle."""
        counters = read_memory_counters()
        update_rrd(self.rrdtool, counters)
        graph_memory(self.rrdtool)
        logger.info(f"Monitored memory metrics into {RRD_DIR}.", source=LOG_SOURCE)
