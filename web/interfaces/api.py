from __future__ import annotations

from typing import Any

from core import iface as iface_module


def get_interfaces() -> dict[str, Any]:
    """Return the current network interface inventory."""
    return iface_module.get_interfaces()


def get_traffic_counters() -> dict[str, Any]:
    """Return current traffic counters for all interfaces."""
    return iface_module.get_traffic_counters()


def get_proc_values() -> dict[str, Any]:
    """Return collected kernel proc settings for interfaces."""
    return iface_module.get_proc_values()


def update_proc_desired_value(iface_name: str, proc_path: str, desired_value: str) -> dict[str, Any]:
    """Persist the user-defined proc value for an interface."""
    return iface_module.update_proc_desired_value(iface_name, proc_path, desired_value)
