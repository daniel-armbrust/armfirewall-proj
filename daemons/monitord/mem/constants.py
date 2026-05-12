"""Constants used by the memory monitoring collector."""

from __future__ import annotations

from pathlib import Path

from ..constants import RRD_DIR


LOG_SOURCE = "monitord/mem/mem.py"
RRD_PATH = RRD_DIR / "mem.rrd"
PROC_MEMINFO = Path("/proc/meminfo")
MEMORY_DS = [
    "mem_total",
    "mem_buffers",
    "mem_cached",
    "mem_free",
    "mem_active",
    "mem_inactive",
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
