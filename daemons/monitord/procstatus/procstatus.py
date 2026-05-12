#!/usr/bin/env python3
"""Process status monitoring collector based on /proc/<pid>/status."""

from __future__ import annotations

from ..constants import RRD_DIR, RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from ..rrd import rrd_needs_creation
from core import log as logger
from core.process import run_command

from .constants import COLLECT_INTERVAL_SECONDS, LOG_SOURCE, MONITORIX_GRAPH_COLORS, PROC_DIR, PROCSTATUS_DS, RRD_PATH
from .models import ProcessCounters


class ProcStatusMonitor:
    """Collect Linux process states and maintain their RRD graph."""

    name = "procstatus"
    interval_seconds = COLLECT_INTERVAL_SECONDS

    def __init__(self, rrdtool: str) -> None:
        """Prepare the process status monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one process status monitoring cycle."""
        counters = read_process_counters()

        update_rrd(self.rrdtool, counters)
        graph_processes(self.rrdtool)
        
        logger.info(f"Monitored process status metrics into {RRD_DIR}.", source=LOG_SOURCE)


def read_process_counters() -> ProcessCounters:
    """Count Linux processes by state using /proc/<pid>/status."""
    states = {
        "S": 0,
        "R": 0,
        "D": 0,
        "Z": 0,
        "T": 0,
        "W": 0,
    }

    for status_path in PROC_DIR.glob("[0-9]*/status"):
        try:
            for line in status_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.startswith("State:"):
                    continue

                parts = line.split()
                
                if len(parts) >= 2 and parts[1] in states:
                    states[parts[1]] += 1
                break
        except OSError:
            continue

    total = sum(states.values())

    return ProcessCounters(
        total=total,
        sleeping=states["S"],
        running=states["R"],
        wait_io=states["D"],
        zombie=states["Z"],
        stopped=states["T"],
        paging=states["W"],
    )


def ensure_rrd(rrdtool: str) -> None:
    """Create the process status RRD file when needed."""
    if not rrd_needs_creation(rrdtool, RRD_PATH, set(PROCSTATUS_DS)):
        return

    heartbeat = max(COLLECT_INTERVAL_SECONDS * 3, 120)

    run_command(
        [
            rrdtool,
            "create",
            str(RRD_PATH),
            "--step",
            str(COLLECT_INTERVAL_SECONDS),
            f"DS:proc_nproc:GAUGE:{heartbeat}:0:U",
            f"DS:proc_npslp:GAUGE:{heartbeat}:0:U",
            f"DS:proc_nprun:GAUGE:{heartbeat}:0:U",
            f"DS:proc_npwio:GAUGE:{heartbeat}:0:U",
            f"DS:proc_npzom:GAUGE:{heartbeat}:0:U",
            f"DS:proc_npstp:GAUGE:{heartbeat}:0:U",
            f"DS:proc_npswp:GAUGE:{heartbeat}:0:U",
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

    logger.info(f"Created process status RRD file: {RRD_PATH}", source=LOG_SOURCE)


def update_rrd(rrdtool: str, counters: ProcessCounters) -> None:
    """Update the process status RRD with the latest raw counters."""
    ensure_rrd(rrdtool)
    
    values = [
        counters.total,
        counters.sleeping,
        counters.running,
        counters.wait_io,
        counters.zombie,
        counters.stopped,
        counters.paging,
    ]

    update_value = "N:" + ":".join(str(value) for value in values)
    
    run_command([rrdtool, "update", str(RRD_PATH), update_value])


def graph_processes(rrdtool: str) -> None:
    """Generate Linux process state graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "procstatus-processes.png"
    
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
                f"Process states - {period_label}",
                "--vertical-label",
                "Processes",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:nproc={RRD_PATH}:proc_nproc:AVERAGE",
                f"DEF:npslp={RRD_PATH}:proc_npslp:AVERAGE",
                f"DEF:nprun={RRD_PATH}:proc_nprun:AVERAGE",
                f"DEF:npwio={RRD_PATH}:proc_npwio:AVERAGE",
                f"DEF:npzom={RRD_PATH}:proc_npzom:AVERAGE",
                f"DEF:npstp={RRD_PATH}:proc_npstp:AVERAGE",
                f"DEF:npswp={RRD_PATH}:proc_npswp:AVERAGE",
                "AREA:npslp#448844:Sleeping",
                "LINE2:npwio#EE44EE:Wait I/O",
                "LINE2:npzom#00EEEE:Zombie",
                "LINE2:npstp#EEEE00:Stopped",
                "LINE2:npswp#0000EE:Paging",
                "LINE2:nprun#EE0000:Running",
                "COMMENT: \\n",
                "LINE2:nproc#888888:Total Processes",
            ]
        )