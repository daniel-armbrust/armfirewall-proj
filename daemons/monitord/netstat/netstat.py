#!/usr/bin/env python3
"""Socket state monitoring collector based on Monitorix netstat metrics."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import fields
from pathlib import Path

from ..constants import RRD_DIR
from ..rrd import rrd_needs_creation
from core import log as logger
from core.process import run_command

from .constants import (
    COLLECT_INTERVAL_SECONDS,
    NETSTAT_DS,
    LOG_SOURCE,
    PROC_TCP4,
    PROC_TCP6,
    PROC_TCP_STATE_MAP,
    PROC_UDP4,
    PROC_UDP6,
    RRD_PATH,
    SS_TCP_STATE_MAP,
    TCP_STATES,
)
from .graphs import generate_graphs
from .models import FamilySocketCounters, SocketCounters


class NetstatMonitor:
    """Collect socket state metrics and maintain their RRD graphs."""

    name = "netstat"
    interval_seconds = COLLECT_INTERVAL_SECONDS

    def __init__(self, rrdtool: str) -> None:
        """Prepare the netstat monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one netstat monitoring cycle."""
        counters = read_socket_counters()
        
        update_rrd(self.rrdtool, counters)
        generate_graphs(self.rrdtool)
        
        logger.info(f"Monitored socket state metrics into {RRD_DIR}.", source=LOG_SOURCE)


def add_tcp_state(counters: FamilySocketCounters, state: str) -> None:
    """Increment one TCP state counter."""
    if not hasattr(counters, state):
        counters.unknown += 1
        return
    
    setattr(counters, state, getattr(counters, state) + 1)


def collect_with_ss(family: str, counters: FamilySocketCounters) -> bool:
    """Collect socket counters through ss for one address family."""
    ss_path = shutil.which("ss")
   
    if not ss_path:
        return False

    result = subprocess.run(
        [ss_path, "-naut", "-f", family],
        check=False,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        return False

    for line in result.stdout.splitlines():
        parts = line.split()
        
        if len(parts) < 2 or parts[0].lower() == "netid":
            continue
        
        proto = parts[0].lower()
        state = parts[1].upper()
        
        if proto == "tcp":
            add_tcp_state(counters, SS_TCP_STATE_MAP.get(state, "unknown"))
        elif proto == "udp":
            counters.udp += 1
    
    return True


def collect_tcp_proc(path: Path, counters: FamilySocketCounters) -> None:
    """Collect TCP state counters from one /proc/net/tcp file."""
    if not path.exists():
        return
    
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split()
        
        if len(parts) < 4:
            continue
        
        add_tcp_state(counters, PROC_TCP_STATE_MAP.get(parts[3].upper(), "unknown"))


def collect_udp_proc(path: Path, counters: FamilySocketCounters) -> None:
    """Collect UDP socket counters from one /proc/net/udp file."""
    if not path.exists():
        return
    
    counters.udp += sum(1 for line in path.read_text(encoding="utf-8").splitlines()[1:] if line.strip())


def collect_with_proc() -> SocketCounters:
    """Collect socket counters from Linux /proc/net files."""
    ipv4 = FamilySocketCounters()
    ipv6 = FamilySocketCounters()
    
    collect_tcp_proc(PROC_TCP4, ipv4)
    collect_tcp_proc(PROC_TCP6, ipv6)
    collect_udp_proc(PROC_UDP4, ipv4)
    collect_udp_proc(PROC_UDP6, ipv6)
    
    return SocketCounters(ipv4=ipv4, ipv6=ipv6)


def read_socket_counters() -> SocketCounters:
    """Read socket counters with ss and fall back to /proc when needed."""
    ipv4 = FamilySocketCounters()
    ipv6 = FamilySocketCounters()
    ipv4_ok = collect_with_ss("inet", ipv4)
    ipv6_ok = collect_with_ss("inet6", ipv6)
    
    if ipv4_ok and ipv6_ok:
        return SocketCounters(ipv4=ipv4, ipv6=ipv6)
    
    return collect_with_proc()


def ensure_rrd(rrdtool: str) -> None:
    """Create the netstat RRD file when it does not exist or has an old schema."""
    if not rrd_needs_creation(rrdtool, RRD_PATH, set(NETSTAT_DS)):
        return

    heartbeat = max(COLLECT_INTERVAL_SECONDS * 3, 120)
    data_sources = [f"DS:{source}:GAUGE:{heartbeat}:0:U" for source in NETSTAT_DS]
    
    run_command(
        [
            rrdtool,
            "create",
            str(RRD_PATH),
            "--step",
            str(COLLECT_INTERVAL_SECONDS),
            *data_sources,
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
    
    logger.info(f"Created netstat RRD file: {RRD_PATH}", source=LOG_SOURCE)


def family_values(counters: FamilySocketCounters) -> list[int]:
    """Return counter values in the RRD data source order for one family."""
    return [int(getattr(counters, field.name)) for field in fields(FamilySocketCounters)]


def update_rrd(rrdtool: str, counters: SocketCounters) -> None:
    """Update the netstat RRD with the latest socket counters."""
    ensure_rrd(rrdtool)
    
    values = [*family_values(counters.ipv4), *family_values(counters.ipv6)]
    
    run_command([rrdtool, "update", str(RRD_PATH), "N:" + ":".join(str(value) for value in values)])