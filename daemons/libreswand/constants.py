"""Constants used by the Libreswan work request executor."""

from __future__ import annotations

from core.constants import CONF_DIR, LIBRESWAN_DB_PATH, SUPERVISOR_CONF, WORK_REQUEST_DB_PATH


LIBRESWAN_CONFIG_DIR = CONF_DIR / "libreswan"
LIBRESWAN_IPSEC_CONF = LIBRESWAN_CONFIG_DIR / "ipsec.conf"
LIBRESWAN_SECRETS = LIBRESWAN_CONFIG_DIR / "ipsec.secrets"

IPSEC_COMMAND = "ipsec"
IPSEC_TIMEOUT_SECONDS = 45
SUPERVISORCTL_COMMAND = "supervisorctl"
SUPERVISOR_TIMEOUT_SECONDS = 60
LIBRESWAN_SERVICE_NAME = "libreswan"

LOG_SOURCE = "libreswand/libreswand.py"
