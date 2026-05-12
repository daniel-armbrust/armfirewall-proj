#!/usr/bin/env python3
"""Socket state monitoring collector based on Monitorix netstat metrics."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import fields
from pathlib import Path

from ..constants import COLLECT_INTERVAL_SECONDS, RRD_DIR, RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from core import log as logger

from .constants import (
    NETSTAT_DS,
    LOG_SOURCE,
    MONITORIX_GRAPH_COLORS,
    PROC_TCP4,
    PROC_TCP6,
    PROC_TCP_STATE_MAP,
    PROC_UDP4,
    PROC_UDP6,
    RRD_PATH,
    SS_TCP_STATE_MAP,
    TCP_STATES,
)
from .models import FamilySocketCounters, SocketCounters


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
    if RRD_PATH.exists() and rrd_data_sources(rrdtool, RRD_PATH) != set(NETSTAT_DS):
        RRD_PATH.unlink()

    if RRD_PATH.exists():
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


def graph_tcp_family(rrdtool: str, family: str, title: str, base_name: str) -> None:
    """Generate the main TCP state graph for one address family."""
    prefix = f"nstat{family}"
    base_path = RRD_IMG_DIR / base_name
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
                f"{title} - {period_label}",
                "--vertical-label",
                "Connections",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:closed={RRD_PATH}:{prefix}_closed:AVERAGE",
                f"DEF:listen={RRD_PATH}:{prefix}_listen:AVERAGE",
                f"DEF:synsent={RRD_PATH}:{prefix}_synsent:AVERAGE",
                f"DEF:synrecv={RRD_PATH}:{prefix}_synrecv:AVERAGE",
                f"DEF:estblshd={RRD_PATH}:{prefix}_estblshd:AVERAGE",
                f"DEF:finwait1={RRD_PATH}:{prefix}_finwait1:AVERAGE",
                f"DEF:finwait2={RRD_PATH}:{prefix}_finwait2:AVERAGE",
                "LINE2:closed#FFA500:CLOSED",
                "GPRINT:closed:LAST:        Current\\: %3.0lf",
                "GPRINT:closed:AVERAGE: Average\\: %3.0lf",
                "GPRINT:closed:MIN: Min\\: %3.0lf",
                "GPRINT:closed:MAX: Max\\: %3.0lf\\n",
                "LINE2:listen#44EEEE:LISTEN",
                "GPRINT:listen:LAST:        Current\\: %3.0lf",
                "GPRINT:listen:AVERAGE: Average\\: %3.0lf",
                "GPRINT:listen:MIN: Min\\: %3.0lf",
                "GPRINT:listen:MAX: Max\\: %3.0lf\\n",
                "LINE2:synsent#44EE44:SYN_SENT",
                "GPRINT:synsent:LAST:      Current\\: %3.0lf",
                "GPRINT:synsent:AVERAGE: Average\\: %3.0lf",
                "GPRINT:synsent:MIN: Min\\: %3.0lf",
                "GPRINT:synsent:MAX: Max\\: %3.0lf\\n",
                "LINE2:synrecv#4444EE:SYN_RECV",
                "GPRINT:synrecv:LAST:      Current\\: %3.0lf",
                "GPRINT:synrecv:AVERAGE: Average\\: %3.0lf",
                "GPRINT:synrecv:MIN: Min\\: %3.0lf",
                "GPRINT:synrecv:MAX: Max\\: %3.0lf\\n",
                "LINE2:estblshd#EE4444:ESTABLISHED",
                "GPRINT:estblshd:LAST:   Current\\: %3.0lf",
                "GPRINT:estblshd:AVERAGE: Average\\: %3.0lf",
                "GPRINT:estblshd:MIN: Min\\: %3.0lf",
                "GPRINT:estblshd:MAX: Max\\: %3.0lf\\n",
                "LINE2:finwait1#EE44EE:FIN_WAIT1",
                "GPRINT:finwait1:LAST:     Current\\: %3.0lf",
                "GPRINT:finwait1:AVERAGE: Average\\: %3.0lf",
                "GPRINT:finwait1:MIN: Min\\: %3.0lf",
                "GPRINT:finwait1:MAX: Max\\: %3.0lf\\n",
                "LINE2:finwait2#EEEE44:FIN_WAIT2",
                "GPRINT:finwait2:LAST:     Current\\: %3.0lf",
                "GPRINT:finwait2:AVERAGE: Average\\: %3.0lf",
                "GPRINT:finwait2:MIN: Min\\: %3.0lf",
                "GPRINT:finwait2:MAX: Max\\: %3.0lf\\n",
            ]
        )


def graph_tcp_closing_timewait(rrdtool: str) -> None:
    """Generate TCP closing and time-wait graphs for both families."""
    base_path = RRD_IMG_DIR / "netstat-tcp-closing-timewait.png"
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
                f"TCP CLOSING and TIME_WAIT states - {period_label}",
                "--vertical-label",
                "Connections",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:i4_closing={RRD_PATH}:nstat4_closing:AVERAGE",
                f"DEF:i6_closing={RRD_PATH}:nstat6_closing:AVERAGE",
                f"DEF:i4_timewait={RRD_PATH}:nstat4_timewait:AVERAGE",
                f"DEF:i6_timewait={RRD_PATH}:nstat6_timewait:AVERAGE",
                "LINE2:i4_closing#44EEEE:CLOSING ipv4",
                "GPRINT:i4_closing:LAST:         Current\\: %3.0lf\\n",
                "LINE2:i6_closing#4444EE:CLOSING ipv6",
                "GPRINT:i6_closing:LAST:         Current\\: %3.0lf\\n",
                "LINE2:i4_timewait#44EE44:TIME_WAIT ipv4",
                "GPRINT:i4_timewait:LAST:       Current\\: %3.0lf\\n",
                "LINE2:i6_timewait#448844:TIME_WAIT ipv6",
                "GPRINT:i6_timewait:LAST:       Current\\: %3.0lf\\n",
            ]
        )


def graph_tcp_wait_unknown(rrdtool: str) -> None:
    """Generate TCP wait and unknown state graphs for both families."""
    base_path = RRD_IMG_DIR / "netstat-tcp-wait-unknown.png"
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
                f"TCP wait and unknown states - {period_label}",
                "--vertical-label",
                "Connections",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:i4_closewait={RRD_PATH}:nstat4_closewait:AVERAGE",
                f"DEF:i6_closewait={RRD_PATH}:nstat6_closewait:AVERAGE",
                f"DEF:i4_lastack={RRD_PATH}:nstat4_lastack:AVERAGE",
                f"DEF:i6_lastack={RRD_PATH}:nstat6_lastack:AVERAGE",
                f"DEF:i4_unknown={RRD_PATH}:nstat4_unknown:AVERAGE",
                f"DEF:i6_unknown={RRD_PATH}:nstat6_unknown:AVERAGE",
                "LINE2:i4_closewait#44EEEE:CLOSE_WAIT ipv4",
                "GPRINT:i4_closewait:LAST:      Current\\: %3.0lf\\n",
                "LINE2:i6_closewait#4444EE:CLOSE_WAIT ipv6",
                "GPRINT:i6_closewait:LAST:      Current\\: %3.0lf\\n",
                "LINE2:i4_lastack#44EE44:LAST_ACK ipv4",
                "GPRINT:i4_lastack:LAST:        Current\\: %3.0lf\\n",
                "LINE2:i6_lastack#448844:LAST_ACK ipv6",
                "GPRINT:i6_lastack:LAST:        Current\\: %3.0lf\\n",
                "LINE2:i4_unknown#EEEE44:UNKNOWN ipv4",
                "GPRINT:i4_unknown:LAST:         Current\\: %3.0lf\\n",
                "LINE2:i6_unknown#FFA500:UNKNOWN ipv6",
                "GPRINT:i6_unknown:LAST:         Current\\: %3.0lf\\n",
            ]
        )


def graph_udp(rrdtool: str) -> None:
    """Generate UDP socket graphs for both families."""
    base_path = RRD_IMG_DIR / "netstat-udp.png"
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
                f"UDP sockets - {period_label}",
                "--vertical-label",
                "Listen",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:i4_udp={RRD_PATH}:nstat4_udp:AVERAGE",
                f"DEF:i6_udp={RRD_PATH}:nstat6_udp:AVERAGE",
                "LINE2:i4_udp#EE44EE:UDP ipv4",
                "GPRINT:i4_udp:LAST:             Current\\: %3.0lf\\n",
                "LINE2:i6_udp#963C74:UDP ipv6",
                "GPRINT:i6_udp:LAST:             Current\\: %3.0lf\\n",
            ]
        )


def generate_graphs(rrdtool: str) -> None:
    """Generate all netstat graph images."""
    graph_tcp_family(rrdtool, "4", "IPv4 TCP socket states", "netstat-ipv4-tcp.png")
    graph_tcp_family(rrdtool, "6", "IPv6 TCP socket states", "netstat-ipv6-tcp.png")
    graph_tcp_closing_timewait(rrdtool)
    graph_tcp_wait_unknown(rrdtool)
    graph_udp(rrdtool)


class NetstatMonitor:
    """Collect socket state metrics and maintain their RRD graphs."""

    name = "netstat"

    def __init__(self, rrdtool: str) -> None:
        """Prepare the netstat monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one netstat monitoring cycle."""
        counters = read_socket_counters()
        update_rrd(self.rrdtool, counters)
        generate_graphs(self.rrdtool)
        logger.info(f"Monitored socket state metrics into {RRD_DIR}.", source=LOG_SOURCE)
