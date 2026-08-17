"""Constants used by the Dnsmasq work request executor."""

from __future__ import annotations

from core.constants import DB_DIR, WORK_REQUEST_DB_PATH


DNSMASQ_DB_PATH = DB_DIR / "dnsmasq.db"

LOG_SOURCE = "dnsmasq/dnsmasq.py"
