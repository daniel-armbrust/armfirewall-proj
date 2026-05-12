"""Shared RRD helpers used by monitoring collectors."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def rrd_data_sources(rrdtool: str, rrd_path: Path) -> set[str]:
    """Return the data source names currently stored in an RRD file."""
    result = subprocess.run([rrdtool, "info", str(rrd_path)], check=True, text=True, capture_output=True)
    sources: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("ds["):
            continue
        sources.add(line.split("[", 1)[1].split("]", 1)[0])
    return sources


def rrd_needs_creation(rrdtool: str, rrd_path: Path, expected_sources: set[str]) -> bool:
    """Remove stale RRD files and report whether a new file must be created."""
    if rrd_path.exists() and rrd_data_sources(rrdtool, rrd_path) != expected_sources:
        rrd_path.unlink()

    return not rrd_path.exists()


def rrd_label(value: str) -> str:
    """Escape one value for use as an RRD graph label."""
    return value.replace("\\", "\\\\").replace(":", "\\:")


def rrd_safe_name(value: str, *, default: str = "unknown", root_name: str = "root") -> str:
    """Return a filesystem-safe name for RRD and graph image paths."""
    if value == "/":
        return root_name
    sanitized = value.strip("/").replace("/", "_")
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", sanitized)
    return sanitized.strip("_") or default
