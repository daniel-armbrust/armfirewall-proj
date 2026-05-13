"""Constants used by the Link Failover daemon."""

from __future__ import annotations

import re

from core.constants import DB_DIR

LINKFAILOVER_DB_PATH = DB_DIR / "linkfailover.db"
LOG_SOURCE = "linkfailoverd.py"
PING_TIME_RE = re.compile(r"time[=<]([0-9.]+)\s*ms")
