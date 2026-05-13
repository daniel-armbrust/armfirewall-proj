"""Constants used by the service management executor."""

from __future__ import annotations

from core.constants import SUPERVISOR_CONF

LOG_SOURCE = "svcmgmtd.py"

PROTECTED_SERVICES = {
    "armfirewall-api",
    "armfirewall-workreqd",
    "armfirewall-ifaced",
}

RESTARTABLE_PROTECTED_SERVICES = {
    "armfirewall-api",
}
