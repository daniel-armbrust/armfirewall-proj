#!/usr/bin/env python3
"""Interface monitoring collector for ArmFirewall."""

from __future__ import annotations

import time
from pathlib import Path

from ..constants import RRD_DIR
from ..rrd import rrd_needs_creation
from core import db
from core import log as logger
from core.constants import IFACE_DB_PATH
from core.process import run_command

from .constants import COLLECT_INTERVAL_SECONDS, INTERFACE_DS, LOG_SOURCE, PROC_NET_DEV
from .graphs import generate_graphs, rrd_path_for_iface
from .models import CounterSnapshot, InterfaceCounters


class InterfaceMonitor:
    """Collect interface counters and maintain their RRD graphs."""

    name = "iface"
    interval_seconds = COLLECT_INTERVAL_SECONDS

    def __init__(self, rrdtool: str) -> None:
        """Prepare the interface monitor dependencies."""
        self.rrdtool = rrdtool
        self.previous: dict[str, CounterSnapshot] = {}

    def collect(self) -> None:
        """Run one interface monitoring cycle."""
        self.previous = collect_once(self.rrdtool, self.previous)


def monitored_interfaces() -> list[str]:
    """Read the monitored interface names from iface.db."""
    rows = db.fetch_all(
        """
        SELECT name
        FROM ifaces
        ORDER BY
            CASE role
                WHEN 'LAN' THEN 1
                WHEN 'WAN' THEN 2
                ELSE 3
            END,
            name
        """,
        db_path=IFACE_DB_PATH,
    )
    
    return [str(row["name"]) for row in rows if row.get("name")]


def parse_proc_net_dev() -> dict[str, InterfaceCounters]:
    """Parse /proc/net/dev into interface counter objects."""
    counters: dict[str, InterfaceCounters] = {}

    for line in PROC_NET_DEV.read_text().splitlines()[2:]:
        if ":" not in line:
            continue

        iface_name, raw_values = line.split(":", 1)
        values = raw_values.split()
        
        if len(values) < 16:
            continue

        counters[iface_name.strip()] = InterfaceCounters(
            rx_bytes=int(values[0]),
            rx_packets=int(values[1]),
            rx_errors=int(values[2]),
            rx_dropped=int(values[3]),
            tx_bytes=int(values[8]),
            tx_packets=int(values[9]),
            tx_errors=int(values[10]),
            tx_dropped=int(values[11]),
        )

    return counters


def ensure_rrd(rrdtool: str, iface_name: str) -> Path:
    """Create the interface RRD file when it does not exist."""
    rrd_path = rrd_path_for_iface(iface_name)
    
    if not rrd_needs_creation(rrdtool, rrd_path, INTERFACE_DS):
        return rrd_path

    heartbeat = max(COLLECT_INTERVAL_SECONDS * 3, 120)
    
    run_command(
        [
            rrdtool,
            "create",
            str(rrd_path),
            "--step",
            str(COLLECT_INTERVAL_SECONDS),
            f"DS:rx_bytes:GAUGE:{heartbeat}:0:U",
            f"DS:tx_bytes:GAUGE:{heartbeat}:0:U",
            f"DS:rx_packets:GAUGE:{heartbeat}:0:U",
            f"DS:tx_packets:GAUGE:{heartbeat}:0:U",
            f"DS:rx_errors:GAUGE:{heartbeat}:0:U",
            f"DS:tx_errors:GAUGE:{heartbeat}:0:U",
            f"DS:rx_dropped:GAUGE:{heartbeat}:0:U",
            f"DS:tx_dropped:GAUGE:{heartbeat}:0:U",
            "RRA:AVERAGE:0.5:1:8640",
            "RRA:AVERAGE:0.5:6:10080",
            "RRA:AVERAGE:0.5:30:1488",
            "RRA:MAX:0.5:1:8640",
            "RRA:MAX:0.5:6:10080",
            "RRA:MAX:0.5:30:1488",
            "RRA:LAST:0.5:1:8640",
            "RRA:LAST:0.5:6:10080",
            "RRA:LAST:0.5:30:1488",
        ]
    )

    logger.info(f"Created RRD file for interface {iface_name}: {rrd_path}", source=LOG_SOURCE)
    
    return rrd_path


def positive_rate(current: int, previous: int, elapsed: float) -> float:
    """Calculate a non-negative per-second counter rate."""
    if elapsed <= 0 or current < previous:
        return 0.0
    
    return (current - previous) / elapsed


def rates_from_snapshots(current: CounterSnapshot, previous: CounterSnapshot | None) -> list[float]:
    """Build the ordered RRD update values from two snapshots."""
    if previous is None:
        return [0.0] * 8

    elapsed = current.timestamp - previous.timestamp
    now = current.counters
    old = previous.counters
    
    return [
        positive_rate(now.rx_bytes, old.rx_bytes, elapsed),
        positive_rate(now.tx_bytes, old.tx_bytes, elapsed),
        positive_rate(now.rx_packets, old.rx_packets, elapsed),
        positive_rate(now.tx_packets, old.tx_packets, elapsed),
        positive_rate(now.rx_errors, old.rx_errors, elapsed),
        positive_rate(now.tx_errors, old.tx_errors, elapsed),
        positive_rate(now.rx_dropped, old.rx_dropped, elapsed),
        positive_rate(now.tx_dropped, old.tx_dropped, elapsed),
    ]


def update_rrd(rrdtool: str, iface_name: str, snapshot: CounterSnapshot, previous: CounterSnapshot | None) -> None:
    """Update one interface RRD with the latest calculated rates."""
    rrd_path = ensure_rrd(rrdtool, iface_name)
    values = rates_from_snapshots(snapshot, previous)
    update_value = "N:" + ":".join(f"{value:.6f}" for value in values)
    run_command([rrdtool, "update", str(rrd_path), update_value])


def collect_once(rrdtool: str, previous: dict[str, CounterSnapshot]) -> dict[str, CounterSnapshot]:
    """Collect one monitoring cycle and return the latest snapshots."""
    interfaces = monitored_interfaces()
    proc_counters = parse_proc_net_dev()
    current: dict[str, CounterSnapshot] = {}
    monitored_count = 0

    for iface_name in interfaces:
        counters = proc_counters.get(iface_name)
        
        if counters is None:
            logger.warning(f"Interface {iface_name} is in iface.db but not in /proc/net/dev.", source=LOG_SOURCE)
            continue

        snapshot = CounterSnapshot(time.time(), counters)
        update_rrd(rrdtool, iface_name, snapshot, previous.get(iface_name))
        generate_graphs(rrdtool, iface_name)
        current[iface_name] = snapshot
        monitored_count += 1

    logger.info(f"Monitored {monitored_count} interfaces into {RRD_DIR}.", source=LOG_SOURCE)

    return current
