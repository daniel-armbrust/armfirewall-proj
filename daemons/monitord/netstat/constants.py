"""Constants used by the socket state monitoring collector."""

from __future__ import annotations

import os
from pathlib import Path

from ..constants import RRD_DIR


LOG_SOURCE = "monitord/netstat/netstat.py"

COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFW_MONITORD_NETSTAT_INTERVAL", "15"))

RRD_PATH = RRD_DIR / "netstat.rrd"

PROC_TCP4 = Path("/proc/net/tcp")

PROC_TCP6 = Path("/proc/net/tcp6")

PROC_UDP4 = Path("/proc/net/udp")

PROC_UDP6 = Path("/proc/net/udp6")

TCP_STATES = [
    "closed",
    "listen",
    "synsent",
    "synrecv",
    "estblshd",
    "finwait1",
    "finwait2",
    "closing",
    "timewait",
    "closewait",
    "lastack",
    "unknown",
]

EXTRA_VALUES = ["val1", "val2", "val3", "val4", "val5"]

NETSTAT_DS = [f"nstat{family}_{state}" for family in ("4", "6") for state in [*TCP_STATES, "udp", *EXTRA_VALUES]]

SS_TCP_STATE_MAP = {
    "UNCONN": "closed",
    "LISTEN": "listen",
    "SYN-SENT": "synsent",
    "SYN-RECV": "synrecv",
    "ESTAB": "estblshd",
    "ESTABLISHED": "estblshd",
    "FIN-WAIT-1": "finwait1",
    "FIN-WAIT-2": "finwait2",
    "CLOSING": "closing",
    "TIME-WAIT": "timewait",
    "CLOSE-WAIT": "closewait",
    "LAST-ACK": "lastack",
    "UNKNOWN": "unknown",
}

PROC_TCP_STATE_MAP = {
    "01": "estblshd",
    "02": "synsent",
    "03": "synrecv",
    "04": "finwait1",
    "05": "finwait2",
    "06": "timewait",
    "07": "closed",
    "08": "closewait",
    "09": "lastack",
    "0A": "listen",
    "0B": "closing",
}

MONITORIX_GRAPH_COLORS = [
    "--color=CANVAS#000000",
    "--color=BACK#101010",
    "--color=FONT#C0C0C0",
    "--color=MGRID#80C080",
    "--color=GRID#808020",
    "--color=FRAME#808080",
    "--color=ARROW#FFFFFF",
    "--color=SHADEA#404040",
    "--color=SHADEB#404040",
    "--color=AXIS#101010",
]
