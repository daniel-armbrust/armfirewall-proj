"""Shared operating system inspection helpers."""

from __future__ import annotations

import os
import platform
from typing import Any

from core import db
from core.cpu import read_cpu_model, read_cpu_usage_percent
from core.constants import SYSTEM_DB_PATH
from core.disk import disk_status
from core.iface import bytes_label
from core.mem import read_memory_status
from core.process import count_processes


def get_hostname() -> str:
    """Return the current system hostname."""
    return platform.node() or "unknown"


def read_system_status() -> dict[str, Any]:
    """Read operating-system status values for SystemCollector."""
    architecture = platform.machine() or "unknown"
    os_name = " ".join(
        part for part in (platform.system(), platform.release()) if part
    )

    return {
        "cpu_model": read_cpu_model(),
        "cpu_count": os.cpu_count() or 0,
        "cpu_usage_percent": read_cpu_usage_percent(),
        "architecture": architecture,
        "platform": platform.platform(),
        "os": os_name,
        "memory": read_memory_status(),
        "process_count": count_processes(),
        "root_disk": disk_status("/"),
    }


def get_system_status() -> dict[str, Any]:
    """Return the latest persisted system snapshot for the web API."""
    with db.connection(SYSTEM_DB_PATH) as conn:
        row = db.fetch_one_on(conn, "SELECT * FROM system_snapshot WHERE id = 1")
    if row is None:
        raise RuntimeError("System snapshot is not available.")
    total = int(row["memory_total_bytes"])
    used = int(row["memory_used_bytes"])
    available = int(row["memory_available_bytes"])
    disk_total = int(row["root_disk_total_bytes"])
    disk_used = int(row["root_disk_used_bytes"])
    disk_free = int(row["root_disk_free_bytes"])
    return {
        "hostname": str(row["hostname"]),
        "cpu_model": str(row["cpu_model"]),
        "cpu_count": int(row["cpu_count"]),
        "cpu_usage_percent": float(row["cpu_usage_percent"]),
        "architecture": str(row["architecture"]),
        "platform": str(row["platform"]),
        "os": str(row["os_name"]),
        "process_count": int(row["process_count"]),
        "collected_at": str(row["collected_at"]),
        "memory": {
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": available,
            "used_percent": round((used / total) * 100, 1) if total else 0,
            "total_label": bytes_label(total),
            "used_label": bytes_label(used),
            "available_label": bytes_label(available),
        },
        "root_disk": {
            "path": "/",
            "total_bytes": disk_total,
            "used_bytes": disk_used,
            "free_bytes": disk_free,
            "used_percent": round((disk_used / disk_total) * 100, 1)
            if disk_total
            else 0,
            "total_label": bytes_label(disk_total),
            "used_label": bytes_label(disk_used),
            "free_label": bytes_label(disk_free),
        },
    }
