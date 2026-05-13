"""Shared disk inspection helpers."""

from __future__ import annotations

import shutil
from typing import Any

from core.iface import bytes_label


def disk_status(path: str = "/") -> dict[str, Any]:
    """Return disk usage for one filesystem path."""
    usage = shutil.disk_usage(path)
    used = usage.total - usage.free
    percent = round((used / usage.total) * 100, 1) if usage.total else 0

    return {
        "path": path,
        "total_bytes": usage.total,
        "used_bytes": used,
        "free_bytes": usage.free,
        "used_percent": percent,
        "total_label": bytes_label(usage.total),
        "used_label": bytes_label(used),
        "free_label": bytes_label(usage.free),
    }
