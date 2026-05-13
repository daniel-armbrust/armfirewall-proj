"""Constants used by the policy routing executor."""

from __future__ import annotations

from pathlib import Path

from core.constants import DB_DIR

POLICY_DB_PATH = DB_DIR / "policy-routing.db"
RT_TABLES_PATH = Path("/etc/iproute2/rt_tables")
LOG_SOURCE = "proutesd.py"
PROTECTED_ROUTE_TABLE_IDS = {253, 255}
PROTECTED_ROUTING_TABLE_IDS = {253, 254, 255}
PROTECTED_RULE_PRIORITIES = {0, 32766, 32767}
BASE_RT_TABLES = {
    255: "local",
    254: "main",
    253: "default",
    0: "unspec",
}
