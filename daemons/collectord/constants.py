"""Shared constants for ArmFirewall collection daemon."""

from __future__ import annotations

import os

from core.constants import BIRD_DB_PATH

LOG_SOURCE = "collectord.py"
SCHEDULER_TICK_SECONDS = int(os.environ.get("ARMFW_COLLECTORD_SCHEDULER_TICK", "1"))
BIRD_PROTOCOLS_INTERVAL_SECONDS = int(os.environ.get("ARMFW_COLLECTORD_BIRD_PROTOCOLS_INTERVAL", "5"))
BIRD_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("ARMFW_COLLECTORD_BIRD_COMMAND_TIMEOUT", "5"))
BIRD_COMMAND_RETENTION = int(os.environ.get("ARMFW_COLLECTORD_BIRD_COMMAND_RETENTION", "500"))
BIRDCL_PATH = os.environ.get("ARMFW_BIRDCL_PATH", "/usr/sbin/birdcl")
BIRD_SHOW_PROTOCOLS_COMMAND = [BIRDCL_PATH, "show", "protocols"]
BIRD_RIP_DIAGNOSTIC_COMMANDS = (
    ("status", [BIRDCL_PATH, "show", "protocols", "all", "rip1"]),
    ("learned-routes", [BIRDCL_PATH, "show", "route", "protocol", "rip1"]),
    ("exported-routes", [BIRDCL_PATH, "show", "route", "export", "rip1"]),
)
