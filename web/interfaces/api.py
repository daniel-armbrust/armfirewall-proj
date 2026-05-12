from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core import db
from core import iface as iface_module


def interface_error(exc: Exception, *, write: bool = False) -> HTTPException:
    """Translate interface domain errors to HTTP responses."""
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=503, detail="Interface database is not ready.")
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc) or "Interface data not found.")
    if isinstance(exc, db.DatabaseError):
        detail = "Interface database update failed." if write else "Interface database query failed."
        return HTTPException(status_code=500, detail=detail)
    return HTTPException(status_code=500, detail="Interface operation failed.")


def get_interfaces() -> dict[str, Any]:
    """Return the current network interface inventory."""
    try:
        return iface_module.get_interfaces()
    except (FileNotFoundError, db.DatabaseError) as exc:
        raise interface_error(exc) from exc


def get_traffic_counters() -> dict[str, Any]:
    """Return current traffic counters for all interfaces."""
    try:
        return iface_module.get_traffic_counters()
    except (FileNotFoundError, db.DatabaseError) as exc:
        raise interface_error(exc) from exc


def get_proc_values() -> dict[str, Any]:
    """Return collected kernel proc settings for interfaces."""
    try:
        return iface_module.get_proc_values()
    except (FileNotFoundError, db.DatabaseError) as exc:
        raise interface_error(exc) from exc


def update_proc_desired_value(iface_name: str, proc_path: str, desired_value: str) -> dict[str, Any]:
    """Persist the user-defined proc value for an interface."""
    try:
        return iface_module.update_proc_desired_value(iface_name, proc_path, desired_value)
    except (FileNotFoundError, LookupError, db.DatabaseError) as exc:
        raise interface_error(exc, write=True) from exc
