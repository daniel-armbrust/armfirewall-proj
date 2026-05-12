"""Constants used by the interface monitoring collector."""

from __future__ import annotations

import os
from pathlib import Path


LOG_SOURCE = "monitord/iface/iface.py"

COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFW_MONITORD_IFACE_INTERVAL", "10"))

PROC_NET_DEV = Path("/proc/net/dev")

INTERFACE_DS = {
    "rx_bytes",
    "tx_bytes",
    "rx_packets",
    "tx_packets",
    "rx_errors",
    "tx_errors",
    "rx_dropped",
    "tx_dropped",
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
