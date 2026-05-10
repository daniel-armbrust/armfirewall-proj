#!/usr/bin/env python3
"""Kernel entropy monitoring collector based on /proc entropy data."""

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


LOG_SOURCE = "monitord/entropy.py"
COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFW_MONITORD_INTERVAL", "10"))
RRD_DIR = ROOT_DIR / "rrd"
RRD_IMG_DIR = RRD_DIR / "img"
RRD_PATH = RRD_DIR / "entropy.rrd"
PROC_ENTROPY = Path("/proc/sys/kernel/random/entropy_avail")
ENTROPY_DS = [
    "entropy_available",
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
class EntropyCounters:
    """Hold the available kernel entropy counter."""

    available: int = 0


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


def read_entropy_counters() -> EntropyCounters:
    """Read available kernel entropy from /proc."""
    try:
        available = int(PROC_ENTROPY.read_text(encoding="utf-8").split()[0])
        return EntropyCounters(available=available)
    except (OSError, ValueError, IndexError):
        return EntropyCounters()


def ensure_rrd(rrdtool: str) -> None:
    """Create the entropy RRD file when needed."""
    if RRD_PATH.exists() and rrd_data_sources(rrdtool, RRD_PATH) != set(ENTROPY_DS):
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
            f"DS:entropy_available:GAUGE:{heartbeat}:0:U",
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
    logger.info(f"Created entropy RRD file: {RRD_PATH}", source=LOG_SOURCE)


def update_rrd(rrdtool: str, counters: EntropyCounters) -> None:
    """Update the entropy RRD with the latest raw counter."""
    ensure_rrd(rrdtool)
    run_command([rrdtool, "update", str(RRD_PATH), f"N:{counters.available}"])


def graph_entropy(rrdtool: str) -> None:
    """Generate kernel entropy graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "entropy-entropy.png"
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
                f"Kernel entropy - {period_label}",
                "--vertical-label",
                "Size",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:entropy={RRD_PATH}:entropy_available:AVERAGE",
                "LINE2:entropy#EEEE00:Entropy",
                "GPRINT:entropy:LAST:              Current\\:%5.0lf\\n",
            ]
        )


class EntropyMonitor:
    """Collect kernel entropy metrics and maintain their RRD graph."""

    name = "entropy"

    def __init__(self, rrdtool: str) -> None:
        """Prepare the entropy monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one entropy monitoring cycle."""
        counters = read_entropy_counters()
        update_rrd(self.rrdtool, counters)
        graph_entropy(self.rrdtool)
        logger.info(f"Monitored entropy metrics into {RRD_DIR}.", source=LOG_SOURCE)
