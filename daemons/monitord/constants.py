"""Shared constants for ArmFirewall monitoring collectors."""

from __future__ import annotations

import os

from core.constants import DB_DIR, RRD_DIR, RRD_IMG_DIR

SCHEDULER_TICK_SECONDS = int(os.environ.get("ARMFW_MONITORD_SCHEDULER_TICK", "1"))

LOG_SOURCE = "monitord.py"
