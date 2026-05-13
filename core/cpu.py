"""Shared CPU inspection helpers."""

from __future__ import annotations

import platform
from pathlib import Path

_LAST_CPU_TIMES: tuple[int, int] | None = None


def read_cpu_model() -> str:
    """Return the first useful processor model found by the operating system."""
    cpuinfo = Path("/proc/cpuinfo")
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
    """Return CPU usage percentage since the previous poll."""
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
