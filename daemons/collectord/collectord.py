#!/usr/bin/env python3
"""Persistent daemon that dispatches ArmFirewall OS collectors."""

from __future__ import annotations

import sys
import time

from core import db
from core import log as logger

from .collectors.bird import BirdProtocolsCollector
from .constants import BIRD_DB_PATH, LOG_SOURCE, SCHEDULER_TICK_SECONDS
from .models import Collector


def build_collectors() -> list[Collector]:
    """Create collectors managed by collectord."""
    db.verify_database(BIRD_DB_PATH)
    return [BirdProtocolsCollector()]


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
            collector.collect()
        except Exception as exc:  # noqa: BLE001 - one collector must not stop the daemon.
            logger.error(f"{collector.name} collection cycle failed: {exc}", source=LOG_SOURCE)
        finally:
            next_runs[collector.name] = time.monotonic() + collector_interval(collector)


def main() -> None:
    """Run the collection loop forever."""
    collectors = build_collectors()
    next_runs = {collector.name: 0.0 for collector in collectors}

    logger.info(
        "Starting ArmFirewall collection daemon with per-collector intervals.",
        source=LOG_SOURCE,
    )

    while True:
        run_due_collectors(collectors, next_runs)
        time.sleep(max(SCHEDULER_TICK_SECONDS, 1))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Stopping ArmFirewall collection daemon.", source=LOG_SOURCE)
        sys.exit(0)
