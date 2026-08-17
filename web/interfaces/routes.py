from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from web.interfaces import api as interfaces_api
from web.interfaces import views as interfaces_views


router = APIRouter()


@router.get("/api/interfaces")
def api_interfaces() -> dict[str, Any]:
    """Return the current network interface inventory."""
    return interfaces_api.get_interfaces()


@router.get("/api/traffic-counters")
def api_traffic_counters() -> dict[str, Any]:
    """Return current traffic counters for all interfaces."""
    return interfaces_api.get_traffic_counters()


@router.get("/api/proc")
def api_proc() -> dict[str, Any]:
    """Return collected kernel proc settings for interfaces."""
    return interfaces_api.get_proc_values()


@router.put("/api/proc/desired-value")
async def api_update_proc_desired_value(request: Request) -> dict[str, Any]:
    """Persist a requested proc value and queue its application."""
    payload = await request.json()
    iface_name = str(payload.get("iface_name", "")).strip()
    proc_path = str(payload.get("proc_path", "")).strip()
    desired_value = str(payload.get("desired_value", "")).strip()

    if not iface_name or not proc_path:
        raise HTTPException(status_code=400, detail="iface_name and proc_path are required.")

    return interfaces_api.update_proc_desired_value(iface_name, proc_path, desired_value)


@router.put("/api/interfaces/{iface_name}")
async def api_update_interface(iface_name: str, request: Request) -> dict[str, Any]:
    """Queue one network interface configuration update."""
    return interfaces_api.queue_interface_update(iface_name, await request.json())


@router.get("/network/interfaces", response_class=HTMLResponse)
def network_interfaces(request: Request) -> HTMLResponse:
    """Render the network interfaces page."""
    return interfaces_views.render_interfaces(request)


@router.get("/network/interfaces/{iface_name}/edit", response_class=HTMLResponse)
def network_interface_edit(request: Request, iface_name: str) -> HTMLResponse:
    """Render the edit page for a selected interface."""
    return interfaces_views.render_interface_edit(request, iface_name)
