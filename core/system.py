"""Shared operating system inspection helpers."""

from __future__ import annotations

import os
import platform
from typing import Any

from core.cpu import read_cpu_model, read_cpu_usage_percent
from core.disk import disk_status
from core.mem import read_memory_status
from core.process import count_processes


def get_system_status() -> dict[str, Any]:
    """Return operating system status values."""
    architecture = platform.machine() or "unknown"
    os_name = " ".join(part for part in (platform.system(), platform.release()) if part)
    
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
