"""Shared memory inspection helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.iface import bytes_label


def read_memory_status() -> dict[str, Any]:
    """Return total, used, and available RAM from /proc/meminfo."""
    values: dict[str, int] = {}
    meminfo = Path("/proc/meminfo")
    
    if meminfo.exists():
        for raw_line in meminfo.read_text(errors="ignore").splitlines():
            parts = raw_line.replace(":", "").split()
            
            if len(parts) >= 2 and parts[1].isdigit():
                values[parts[0]] = int(parts[1]) * 1024

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = max(total - available, 0) if total else 0
    percent = round((used / total) * 100, 1) if total else 0

    return {
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
        "used_percent": percent,
        "total_label": bytes_label(total),
        "used_label": bytes_label(used),
        "available_label": bytes_label(available),
    }
