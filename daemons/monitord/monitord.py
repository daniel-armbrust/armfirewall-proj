#!/usr/bin/env python3
"""Persistent daemon that dispatches ArmFirewall monitoring collectors."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Protocol

ROOT_DIR = Path(__file__).resolve().parents[2]
MONITORD_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(MONITORD_DIR) not in sys.path:
    sys.path.insert(0, str(MONITORD_DIR))

from core import log as logger
import entropy
import fs
import iface
import kern
import latency
import loadavg
import mem
import netstat
import procstatus
import uptime


LOG_SOURCE = "monitord.py"
COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFW_MONITORD_INTERVAL", "10"))
RRD_DIR = ROOT_DIR / "rrd"
RRD_IMG_DIR = RRD_DIR / "img"


class MonitorCollector(Protocol):
    """Describe a monitoring collector invoked by the daemon loop."""

    name: str

    def collect(self) -> None:
        """Run one collection cycle."""


def build_collectors() -> list[MonitorCollector]:
    """Create the monitoring collectors managed by monitord."""
    rrdtool = require_rrdtool()
    ensure_directories()
    return [
        iface.InterfaceMonitor(rrdtool),
        latency.LatencyMonitor(rrdtool),
        kern.KernelMonitor(rrdtool),
        loadavg.LoadAvgMonitor(rrdtool),
        entropy.EntropyMonitor(rrdtool),
        uptime.UptimeMonitor(rrdtool),
        mem.MemoryMonitor(rrdtool),
        procstatus.ProcStatusMonitor(rrdtool),
        fs.FilesystemMonitor(rrdtool),
        netstat.NetstatMonitor(rrdtool),
    ]


def require_rrdtool() -> str:
    """Return the rrdtool binary path or fail clearly."""
    rrdtool = shutil.which("rrdtool")
    if not rrdtool:
        raise RuntimeError("rrdtool command was not found.")
    return rrdtool


def ensure_directories() -> None:
    """Create the RRD data and image directories."""
    RRD_DIR.mkdir(parents=True, exist_ok=True)
    RRD_IMG_DIR.mkdir(parents=True, exist_ok=True)


def run_cycle(collectors: list[MonitorCollector]) -> None:
    """Run one monitoring cycle across all configured collectors."""
    for collector in collectors:
        try:
            collector.collect()
        except Exception as exc:  # noqa: BLE001 - one collector must not stop the daemon.
            logger.error(f"{collector.name} monitoring cycle failed: {exc}", source=LOG_SOURCE)


def main() -> None:
    """Run the monitoring loop forever."""
    collectors = build_collectors()
    logger.info(
        f"Starting ArmFirewall monitor daemon with {COLLECT_INTERVAL_SECONDS}s interval.",
        source=LOG_SOURCE,
    )

    while True:
        run_cycle(collectors)
        time.sleep(COLLECT_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
