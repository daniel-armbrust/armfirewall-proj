from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any

from core import db
from core import iface as iface_module


ROOT_DIR = Path(__file__).resolve().parents[2]
_LAST_CPU_TIMES: tuple[int, int] | None = None


def read_conf() -> dict[str, str]:
    """Return interface roles persisted by the installer."""
    values: dict[str, str] = {}
    try:
        rows = db.fetch_all(
            """
            SELECT role, name
            FROM ifaces
            WHERE role IN ('LAN', 'WAN')
            ORDER BY CASE role WHEN 'LAN' THEN 0 WHEN 'WAN' THEN 1 ELSE 2 END, id
            """
        )
    except (FileNotFoundError, db.DatabaseError):
        return values

    for row in rows:
        key = "lan_iface" if row["role"] == "LAN" else "wan_iface"
        values.setdefault(key, str(row["name"]))
    return values


def bytes_label(value: int) -> str:
    """Format a byte count using a compact binary unit."""
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{value} B"


def read_cpu_model() -> str:
    """Return the first useful processor model found by the operating system."""
    cpuinfo = Path("/proc/cpuinfo")
    preferred_keys = ("model name", "hardware", "cpu part", "cpu implementer")
    values: dict[str, str] = {}

    if cpuinfo.exists():
        for raw_line in cpuinfo.read_text(errors="ignore").splitlines():
            if ":" not in raw_line:
                continue
            key, value = raw_line.split(":", 1)
            normalized = key.strip().lower()
            text = value.strip()
            if text and normalized not in values:
                values[normalized] = text

    for key in ("model name", "hardware"):
        value = values.get(key)
        if value and not value.isdigit():
            return value

    implementer = values.get("cpu implementer")
    part = values.get("cpu part")
    architecture = values.get("cpu architecture")
    if implementer or part:
        pieces = ["ARM"]
        if architecture:
            pieces.append(f"architecture {architecture}")
        if implementer:
            pieces.append(f"implementer {implementer}")
        if part:
            pieces.append(f"part {part}")
        return " ".join(pieces)

    return platform.processor() or platform.machine() or "unknown"


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


def read_cpu_times() -> tuple[int, int] | None:
    """Return total and idle CPU jiffies from /proc/stat."""
    stat_path = Path("/proc/stat")
    if not stat_path.exists():
        return None

    first_line = stat_path.read_text(errors="ignore").splitlines()[0]
    parts = first_line.split()
    if not parts or parts[0] != "cpu":
        return None

    values = [int(value) for value in parts[1:] if value.isdigit()]
    if len(values) < 4:
        return None

    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return total, idle


def read_cpu_usage_percent() -> float:
    """Return CPU usage percentage since the previous dashboard poll."""
    global _LAST_CPU_TIMES

    current = read_cpu_times()
    if current is None:
        return 0.0

    if _LAST_CPU_TIMES is None:
        _LAST_CPU_TIMES = current
        return 0.0

    previous_total, previous_idle = _LAST_CPU_TIMES
    current_total, current_idle = current
    _LAST_CPU_TIMES = current

    total_delta = current_total - previous_total
    idle_delta = current_idle - previous_idle
    if total_delta <= 0:
        return 0.0

    used = max(total_delta - idle_delta, 0)
    return round((used / total_delta) * 100, 1)


def count_processes() -> int:
    """Count numeric process directories from /proc."""
    proc = Path("/proc")
    if not proc.exists():
        return 0
    return sum(1 for item in proc.iterdir() if item.name.isdigit())


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


def get_system_status() -> dict[str, Any]:
    """Return system status values for the dashboard."""
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


def get_dashboard() -> dict[str, Any]:
    """Build the data payload consumed by the dashboard page."""
    counters = iface_module.get_traffic_counters()

    return {
        "config": read_conf(),
        "system": get_system_status(),
        "summary": counters["summary"],
        "interfaces": counters["interfaces"],
    }
