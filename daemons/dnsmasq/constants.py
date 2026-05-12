"""Constants used by the Dnsmasq work request executor."""

from __future__ import annotations

from core.constants import CONF_DIR, DB_DIR


DNSMASQ_DB_PATH = DB_DIR / "dnsmasq.db"

WORK_REQUEST_DB_PATH = DB_DIR / "work-requests.db"

DNSMASQ_CONF = CONF_DIR / "dnsmasq.conf"

LOG_SOURCE = "dnsmasq/dnsmasq.py"
