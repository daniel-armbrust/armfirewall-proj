#!/usr/bin/env python3
"""Persistent daemon that dispatches ArmFirewall OS collectors."""

from __future__ import annotations

import sys
import time
from typing import Protocol

from core import log as logger
from core.constants import COLLECTORD_LOG_SOURCE, COLLECTORD_SCHEDULER_TICK_SECONDS

from .collectors.bird import BirdProtocolsCollector
from .collectors.iface import IfaceCollector
from .collectors.neighbor import NeighborCollector
from .collectors.system import SystemCollector


class Collector(Protocol):
    """Describe one collector invoked by the collectord scheduler."""

    name: str
    interval_seconds: int

    def is_available(self) -> bool:
        """Return whether the collector can run on the current appliance."""

    def collect(self) -> None:
        """Run one collection cycle."""


def build_collectors() -> list[Collector]:
    """Create collectors managed by collectord."""
    return [BirdProtocolsCollector(), IfaceCollector(), SystemCollector(), NeighborCollector()]


def collector_interval(collector: Collector) -> int:
    """Return a safe scheduler interval for one collector."""
    return max(int(collector.interval_seconds), 1)


def run_due_collectors(collectors: list[Collector], next_runs: dict[str, float]) -> None:
    """Run each collector only when its own interval is due."""
    now = time.monotonic()

    for collector in collectors:
        if now < next_runs.get(collector.name, 0.0):
            continue
        try:
            if collector.is_available():
                collector.collect()
        except Exception as exc:  # noqa: BLE001 - one collector must not stop the daemon.
            logger.error(f"{collector.name} collection cycle failed: {exc}", source=COLLECTORD_LOG_SOURCE)
        finally:
            next_runs[collector.name] = time.monotonic() + collector_interval(collector)


def main() -> None:
    """Run the collection loop forever."""
    collectors = build_collectors()
    next_runs = {collector.name: 0.0 for collector in collectors}

    logger.info(
        "Starting ArmFirewall collection daemon with per-collector intervals.",
        source=COLLECTORD_LOG_SOURCE,
    )

    while True:
        run_due_collectors(collectors, next_runs)
        time.sleep(max(COLLECTORD_SCHEDULER_TICK_SECONDS, 1))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Stopping ArmFirewall collection daemon.", source=COLLECTORD_LOG_SOURCE)
        sys.exit(0)
