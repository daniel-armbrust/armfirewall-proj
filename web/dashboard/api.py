from __future__ import annotations

from typing import Any

from core import iface as iface_module
from core import system as system_module


def read_conf() -> dict[str, str]:
    """Return interface roles persisted by the installer."""
    return iface_module.get_role_config()


def get_dashboard() -> dict[str, Any]:
    """Build the data payload consumed by the dashboard page."""
    counters = iface_module.get_traffic_counters()

    return {
        "config": read_conf(),
        "system": system_module.get_system_status(),
        "summary": counters["summary"],
        "interfaces": counters["interfaces"],
    }
