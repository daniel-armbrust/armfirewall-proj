#!/usr/bin/env python3
"""Shared graph period helpers for monitoring collectors."""

from __future__ import annotations

from pathlib import Path


GRAPH_PERIODS = [
    ("daily", "Daily", "-1d"),
    ("weekly", "Weekly", "-1w"),
    ("monthly", "Monthly", "-1m"),
    ("yearly", "Yearly", "-1y"),
]


def period_image_path(base_path: Path, period_name: str) -> Path:
    """Return the graph image path for one period."""
    if period_name == "daily":
        return base_path
    return base_path.with_name(f"{base_path.stem}-{period_name}{base_path.suffix}")
