"""Constants used by the kernel monitoring collector."""

from __future__ import annotations

from pathlib import Path

from ..constants import RRD_DIR


LOG_SOURCE = "monitord/kern/kern.py"
RRD_PATH = RRD_DIR / "kern.rrd"
PROC_STAT = Path("/proc/stat")
PROC_DENTRY = Path("/proc/sys/fs/dentry-state")
PROC_FILE_NR = Path("/proc/sys/fs/file-nr")
PROC_INODE_NR = Path("/proc/sys/fs/inode-nr")
KERN_DS = [
    "kern_user",
    "kern_nice",
    "kern_sys",
    "kern_idle",
    "kern_iow",
    "kern_irq",
    "kern_sirq",
    "kern_steal",
    "kern_guest",
    "kern_cs",
    "kern_dentry",
    "kern_file",
    "kern_inode",
    "kern_forks",
    "kern_vforks",
    "kern_val03",
    "kern_val04",
    "kern_val05",
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
