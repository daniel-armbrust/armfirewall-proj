"""Global constants shared across ArmFirewall modules."""

from __future__ import annotations

from datetime import timedelta
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

WEB_DIR = ROOT_DIR / "web"
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

SESSION_COOKIE = "armfw_session"
SESSION_TTL = timedelta(hours=8)
LOGIN_PATH = "/login"
CHANGE_PASSWORD_PATH = "/login/change-password"
LOGOUT_PATH = "/logout"
PUBLIC_PREFIXES = ("/static/",)
AUTH_FLOW_PATHS = {LOGIN_PATH, CHANGE_PASSWORD_PATH}
