"""Constants used by the filesystem monitoring collector."""

from __future__ import annotations

import os
from pathlib import Path


LOG_SOURCE = "monitord/fs/fs.py"

COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFW_MONITORD_FS_INTERVAL", "300"))

PROC_MOUNTINFO = Path("/proc/self/mountinfo")

PROC_DISKSTATS = Path("/proc/diskstats")

RRD_DATA_SOURCES = {"usage_pct", "inode_pct", "io_ops", "io_time_ms"}

PSEUDO_FILESYSTEMS = {
    "autofs",
    "binfmt_misc",
    "bpf",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devpts",
    "devtmpfs",
    "efivarfs",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "proc",
    "pstore",
    "rpc_pipefs",
    "securityfs",
    "selinuxfs",
    "sysfs",
    "tmpfs",
    "tracefs",
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

MONITORIX_FS_LINE_COLORS = [
    "#FFA500",
    "#44EEEE",
    "#44EE44",
    "#4444EE",
    "#448844",
    "#5F04B4",
    "#EE44EE",
    "#EEEE44",
]
