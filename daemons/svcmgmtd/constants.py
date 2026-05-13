"""Constants used by the service management executor."""

from __future__ import annotations

from core.constants import CONF_DIR

SUPERVISOR_CONF = CONF_DIR / "supervisord.conf"
LOG_SOURCE = "svcmgmtd.py"

ALLOWED_SERVICES = {
    "armfirewall-squid": {
        "package": "squid",
        "binary": "/usr/sbin/squid",
    },
}

CONTROLLABLE_SERVICES = {
    "armfirewall-ifaced",
    "armfirewall-monitord",
    "armfirewall-workreqd",
    "armfirewall-dnsmasq",
    "armfirewall-linkfailover",
    "armfirewall-squid",
}

PROTECTED_SERVICES = {
    "armfirewall-api",
    "armfirewall-workreqd",
    "armfirewall-ifaced",
}
