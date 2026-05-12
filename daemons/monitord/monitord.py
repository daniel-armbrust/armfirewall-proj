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

from .constants import LOG_SOURCE, SCHEDULER_TICK_SECONDS
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


def collector_interval(collector: MonitorCollector) -> int:
    """Return a safe scheduler interval for one collector."""
    return max(int(collector.interval_seconds), 1)


def run_due_collectors(collectors: list[MonitorCollector], next_runs: dict[str, float]) -> None:
    """Run each collector only when its own interval is due."""
    now = time.monotonic()

    for collector in collectors:
        if now < next_runs.get(collector.name, 0.0):
            continue
        try:
            collector.collect()
        except Exception as exc:  # noqa: BLE001 - one collector must not stop the daemon.
            logger.error(f"{collector.name} monitoring cycle failed: {exc}", source=LOG_SOURCE)
        finally:
            next_runs[collector.name] = time.monotonic() + collector_interval(collector)


def main() -> None:
    """Run the monitoring loop forever."""
    collectors = build_collectors()
    next_runs = {collector.name: 0.0 for collector in collectors}
    
    logger.info(
        "Starting ArmFirewall monitor daemon with per-collector intervals.",
        source=LOG_SOURCE,
    )

    while True:
        run_due_collectors(collectors, next_runs)
        time.sleep(max(SCHEDULER_TICK_SECONDS, 1))


if __name__ == "__main__":
    main()
