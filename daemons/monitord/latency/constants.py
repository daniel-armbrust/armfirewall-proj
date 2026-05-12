"""Constants used by the latency monitoring collector."""

from __future__ import annotations

import os

from ..constants import DB_DIR


LOG_SOURCE = "monitord/latency/latency.py"

COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFW_MONITORD_LATENCY_INTERVAL", "30"))

LATENCY_DB_PATH = DB_DIR / "latency.db"

LATENCY_DS = {"min", "avg", "max", "loss"}

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
