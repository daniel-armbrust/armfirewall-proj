from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core import db
from core import iface as iface_module
from core.constants import (
    IFACE_PROC_WORK_REQUEST_ACTION,
    IFACE_PROC_WORK_REQUEST_CATEGORY,
    IFACE_PROC_WORK_REQUEST_PRIORITY,
)
from web.workrequests.api import queue_work_request


def interface_error(exc: Exception, *, write: bool = False) -> HTTPException:
    """Translate interface domain errors to HTTP responses."""
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=503, detail="Interface database is not ready.")
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc) or "Interface data not found.")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc) or "Invalid interface value.")
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
    """Persist a proc value and queue its application to the operating system."""
    try:
        result = iface_module.update_proc_desired_value(iface_name, proc_path, desired_value)
        work_request = queue_work_request(
            action=IFACE_PROC_WORK_REQUEST_ACTION,
            category_name=IFACE_PROC_WORK_REQUEST_CATEGORY,
            payload={
                "iface_name": iface_name,
                "proc_path": proc_path,
                "desired_value": desired_value,
            },
            priority=IFACE_PROC_WORK_REQUEST_PRIORITY,
            allowed_actions=(IFACE_PROC_WORK_REQUEST_ACTION,),
            allowed_categories=(IFACE_PROC_WORK_REQUEST_CATEGORY,),
            event_message=f"Queued kernel proc update for {iface_name}: {proc_path}",
        )
        return result | {"work_request": work_request}
    except (FileNotFoundError, LookupError, ValueError, db.DatabaseError) as exc:
        raise interface_error(exc, write=True) from exc


def queue_interface_update(iface_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and queue one network interface configuration update."""
    try:
        current = next((item for item in iface_module.get_interfaces()["interfaces"] if item["name"] == iface_name), None)
        if current is None:
            raise LookupError("Network interface not found.")

        role = str(payload.get("role") or "").strip().upper()
        description = str(payload.get("description") or "").strip()
        protected = int(payload.get("protected"))
        mtu = int(payload.get("mtu"))
        if role not in {"LAN", "WAN", "UNKNOWN"}:
            raise ValueError("Invalid interface role.")
        if protected not in {0, 1}:
            raise ValueError("Invalid protected value.")
        if not 68 <= mtu <= 65535:
            raise ValueError("MTU must be between 68 and 65535.")
        if len(description) > 255:
            raise ValueError("Description must not exceed 255 characters.")

        work_request = queue_work_request(
            action=IFACE_PROC_WORK_REQUEST_ACTION,
            category_name=IFACE_PROC_WORK_REQUEST_CATEGORY,
            payload={
                "operation": "interface_config",
                "iface_name": iface_name,
                "role": role,
                "description": description,
                "protected": protected,
                "mtu": mtu,
            },
            priority=IFACE_PROC_WORK_REQUEST_PRIORITY,
            allowed_actions=(IFACE_PROC_WORK_REQUEST_ACTION,),
            allowed_categories=(IFACE_PROC_WORK_REQUEST_CATEGORY,),
            event_message=f"Queued network interface configuration update for {iface_name}.",
        )
        return {"work_request": work_request}
    except (FileNotFoundError, LookupError, TypeError, ValueError, db.DatabaseError) as exc:
        raise interface_error(exc, write=True) from exc
