#!/usr/bin/env python3
"""Persistent daemon that dispatches ArmFirewall monitoring collectors."""

from __future__ import annotations

import time

from . import entropy
from . import fs
from . import iface
from . import kern
from . import latency
from . import loadavg
from . import mem
from . import netstat
from . import procstatus
from . import uptime
from .constants import COLLECT_INTERVAL_SECONDS, LOG_SOURCE
from .models import MonitorCollector
from .runtime import ensure_directories, require_rrdtool
from core import log as logger


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
