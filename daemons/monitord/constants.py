"""Shared constants for ArmFirewall monitoring collectors."""

from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]

DB_DIR = ROOT_DIR / "db"

RRD_DIR = ROOT_DIR / "rrd"

RRD_IMG_DIR = RRD_DIR / "img"

SCHEDULER_TICK_SECONDS = int(os.environ.get("ARMFW_MONITORD_SCHEDULER_TICK", "1"))

LOG_SOURCE = "monitord.py"
