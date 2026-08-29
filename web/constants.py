"""Constants used by the ArmFirewall web application."""

from __future__ import annotations

from datetime import timedelta

from core.constants import ROOT_DIR


WEB_DIR = ROOT_DIR / "web"
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

SERVICES_STATUS_ACTIONS = {"enable", "disable", "start", "stop", "restart"}
SESSION_COOKIE = "armfw_session"
SESSION_TTL = timedelta(minutes=10)
LOGIN_PATH = "/login"
CHANGE_PASSWORD_PATH = "/login/change-password"
LOGOUT_PATH = "/logout"
PUBLIC_PREFIXES = ("/static/",)
AUTH_FLOW_PATHS = {LOGIN_PATH, CHANGE_PASSWORD_PATH}
