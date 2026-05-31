"""Global constants shared across ArmFirewall modules."""

from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

DB_DIR = ROOT_DIR / "db"
CONF_DIR = ROOT_DIR / "conf"
LOG_DIR = ROOT_DIR / "logs"
SUPERVISOR_CONF = CONF_DIR / "supervisord.conf"
IFACE_DB_PATH = DB_DIR / "iface.db"
LOG_DB_PATH = DB_DIR / "logs.db"
USERS_DB_PATH = DB_DIR / "users.db"
WORK_REQUEST_DB_PATH = DB_DIR / "work-requests.db"
SERVICES_DB_PATH = DB_DIR / "services.db"
DNSMASQ_DB_PATH = DB_DIR / "dnsmasq.db"
LATENCY_DB_PATH = DB_DIR / "latency.db"
LINKFAILOVER_DB_PATH = DB_DIR / "linkfailover.db"
POLICY_ROUTING_DB_PATH = DB_DIR / "policy-routing.db"
LIBRESWAN_DB_PATH = DB_DIR / "libreswan.db"
POLICY_ROUTING_DDL_PATH = DB_DIR / "ddl" / "policy-routing.ddl"

RRD_DIR = ROOT_DIR / "rrd"
RRD_IMG_DIR = RRD_DIR / "img"
