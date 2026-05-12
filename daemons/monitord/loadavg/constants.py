"""Constants used by the load average monitoring collector."""

from __future__ import annotations

from pathlib import Path

from ..constants import RRD_DIR


LOG_SOURCE = "monitord/loadavg/loadavg.py"
RRD_PATH = RRD_DIR / "loadavg.rrd"
PROC_LOADAVG = Path("/proc/loadavg")
LOADAVG_DS = [
    "loadavg_load1",
    "loadavg_load5",
    "loadavg_load15",
]
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
