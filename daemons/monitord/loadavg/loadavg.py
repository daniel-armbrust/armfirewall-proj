#!/usr/bin/env python3
"""Load average monitoring collector based on /proc/loadavg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..constants import COLLECT_INTERVAL_SECONDS, RRD_DIR, RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from core import log as logger

from .constants import LOADAVG_DS, LOG_SOURCE, MONITORIX_GRAPH_COLORS, PROC_LOADAVG, RRD_PATH
from .models import LoadAvgCounters


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


def read_loadavg_counters() -> LoadAvgCounters:
    """Read Linux load average values from /proc/loadavg."""
    try:
        values = PROC_LOADAVG.read_text(encoding="utf-8").split()
        return LoadAvgCounters(float(values[0]), float(values[1]), float(values[2]))
    except (OSError, ValueError, IndexError):
        return LoadAvgCounters()


def ensure_rrd(rrdtool: str) -> None:
    """Create the load average RRD file when needed."""
    if RRD_PATH.exists() and rrd_data_sources(rrdtool, RRD_PATH) != set(LOADAVG_DS):
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
            f"DS:loadavg_load1:GAUGE:{heartbeat}:0:U",
            f"DS:loadavg_load5:GAUGE:{heartbeat}:0:U",
            f"DS:loadavg_load15:GAUGE:{heartbeat}:0:U",
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
    logger.info(f"Created load average RRD file: {RRD_PATH}", source=LOG_SOURCE)


def update_rrd(rrdtool: str, counters: LoadAvgCounters) -> None:
    """Update the load average RRD with the latest raw counters."""
    ensure_rrd(rrdtool)
    values = [
        counters.load1,
        counters.load5,
        counters.load15,
    ]
    update_value = "N:" + ":".join(str(value) for value in values)
    run_command([rrdtool, "update", str(RRD_PATH), update_value])


def graph_loadavg(rrdtool: str) -> None:
    """Generate system load average graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "loadavg-load.png"
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
                f"System load average - {period_label}",
                "--vertical-label",
                "Load average",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:load1={RRD_PATH}:loadavg_load1:AVERAGE",
                f"DEF:load5={RRD_PATH}:loadavg_load5:AVERAGE",
                f"DEF:load15={RRD_PATH}:loadavg_load15:AVERAGE",
                "AREA:load1#4444EE: 1 min average",
                "GPRINT:load1:LAST:  Current\\: %4.2lf",
                "GPRINT:load1:AVERAGE:   Average\\: %4.2lf",
                "GPRINT:load1:MIN:   Min\\: %4.2lf",
                "GPRINT:load1:MAX:   Max\\: %4.2lf\\n",
                "LINE1:load1#0000EE",
                "LINE1:load5#EEEE00: 5 min average",
                "GPRINT:load5:LAST:  Current\\: %4.2lf",
                "GPRINT:load5:AVERAGE:   Average\\: %4.2lf",
                "GPRINT:load5:MIN:   Min\\: %4.2lf",
                "GPRINT:load5:MAX:   Max\\: %4.2lf\\n",
                "LINE1:load15#00EEEE:15 min average",
                "GPRINT:load15:LAST:  Current\\: %4.2lf",
                "GPRINT:load15:AVERAGE:   Average\\: %4.2lf",
                "GPRINT:load15:MIN:   Min\\: %4.2lf",
                "GPRINT:load15:MAX:   Max\\: %4.2lf\\n",
            ]
        )


class LoadAvgMonitor:
    """Collect Linux load average metrics and maintain their RRD graph."""

    name = "loadavg"

    def __init__(self, rrdtool: str) -> None:
        """Prepare the load average monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one load average monitoring cycle."""
        counters = read_loadavg_counters()
        update_rrd(self.rrdtool, counters)
        graph_loadavg(self.rrdtool)
        logger.info(f"Monitored load average metrics into {RRD_DIR}.", source=LOG_SOURCE)
