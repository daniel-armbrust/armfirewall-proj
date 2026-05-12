"""Constants used by the entropy monitoring collector."""

from __future__ import annotations

from pathlib import Path

from ..constants import RRD_DIR


LOG_SOURCE = "monitord/entropy/entropy.py"
RRD_PATH = RRD_DIR / "entropy.rrd"
PROC_ENTROPY = Path("/proc/sys/kernel/random/entropy_avail")
ENTROPY_DS = [
    "entropy_available",
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
