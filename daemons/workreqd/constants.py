"""Constants used by the work request daemon."""

from __future__ import annotations

import os

from core.constants import DB_DIR

WORK_REQUEST_DB_PATH = DB_DIR / "work-requests.db"
CHECK_INTERVAL_SECONDS = int(os.environ.get("ARMFIREWALL_ARMFWORKREQD_INTERVAL", "5"))
BATCH_SIZE = int(os.environ.get("ARMFIREWALL_ARMFWORKREQD_BATCH_SIZE", "10"))
ACTION_TIMEOUT_SECONDS = int(os.environ.get("ARMFIREWALL_ARMFWORKREQD_ACTION_TIMEOUT", "300"))
LOG_SOURCE = "workreqd.py"
