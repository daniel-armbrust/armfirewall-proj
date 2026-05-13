"""Global constants shared across ArmFirewall modules."""

from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

DB_DIR = ROOT_DIR / "db"
CONF_DIR = ROOT_DIR / "conf"
LOG_DIR = ROOT_DIR / "logs"
IFACE_DB_PATH = DB_DIR / "iface.db"
LOG_DB_PATH = DB_DIR / "logs.db"
USERS_DB_PATH = DB_DIR / "users.db"

RRD_DIR = ROOT_DIR / "rrd"
RRD_IMG_DIR = RRD_DIR / "img"
