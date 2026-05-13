"""Shared constants for ArmFirewall monitoring collectors."""

from __future__ import annotations

import os

SCHEDULER_TICK_SECONDS = int(os.environ.get("ARMFW_MONITORD_SCHEDULER_TICK", "1"))

LOG_SOURCE = "monitord.py"
