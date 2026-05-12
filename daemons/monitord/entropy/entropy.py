#!/usr/bin/env python3
"""Kernel entropy monitoring collector based on /proc entropy data."""

from __future__ import annotations

from ..constants import RRD_DIR
from ..rrd import rrd_needs_creation
from core import log as logger
from core.process import run_command

from .constants import COLLECT_INTERVAL_SECONDS, ENTROPY_DS, LOG_SOURCE, PROC_ENTROPY, RRD_PATH
from .graphs import graph_entropy
from .models import EntropyCounters


class EntropyMonitor:
    """Collect kernel entropy metrics and maintain their RRD graph."""

    name = "entropy"
    interval_seconds = COLLECT_INTERVAL_SECONDS

    def __init__(self, rrdtool: str) -> None:
        """Prepare the entropy monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one entropy monitoring cycle."""
        counters = read_entropy_counters()
        
        update_rrd(self.rrdtool, counters)
        graph_entropy(self.rrdtool)
        
        logger.info(f"Monitored entropy metrics into {RRD_DIR}.", source=LOG_SOURCE)


def read_entropy_counters() -> EntropyCounters:
    """Read available kernel entropy from /proc."""
    try:
        available = int(PROC_ENTROPY.read_text(encoding="utf-8").split()[0])
        return EntropyCounters(available=available)
    except (OSError, ValueError, IndexError):
        return EntropyCounters()


def ensure_rrd(rrdtool: str) -> None:
    """Create the entropy RRD file when needed."""
    if not rrd_needs_creation(rrdtool, RRD_PATH, set(ENTROPY_DS)):
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
