from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.services.dnsmasq import dnsmasq as services_dnsmasq_views
from web.services.proxy import proxy as services_proxy_views
from web.services import status as services_status_views


router = APIRouter()


@router.get("/api/services/status")
def api_services_status() -> dict[str, Any]:
    """Return ArmFirewall supervisord service statuses."""
    return services_status_views.services_status()


@router.post("/api/services/status/{service_name}/action")
def api_control_service(service_name: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Control one non-protected ArmFirewall supervisord service."""
    try:
        return services_status_views.control_service(service_name, str(payload.get("action", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/services/status/{service_name}/install")
def api_install_optional_service(service_name: str) -> dict[str, Any]:
    """Queue installation for one optional ArmFirewall service."""
    try:
        return services_status_views.install_optional_service(service_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/services/status/{service_name}/uninstall")
def api_uninstall_optional_service(service_name: str) -> dict[str, Any]:
    """Queue removal for one optional ArmFirewall service."""
    try:
        return services_status_views.uninstall_optional_service(service_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/services/dnsmasq")
def api_dnsmasq_config() -> dict[str, Any]:
    """Return dnsmasq configuration and service status."""
    return services_dnsmasq_views.get_dnsmasq_config()


@router.put("/api/services/dnsmasq")
async def api_save_dnsmasq_config(request: Request) -> dict[str, Any]:
    """Save dnsmasq configuration from the GUI."""
    payload = await request.json()
    return services_dnsmasq_views.save_dnsmasq_config(payload)


@router.post("/api/services/dnsmasq/test")
async def api_test_dnsmasq_config(request: Request) -> dict[str, Any]:
    """Validate dnsmasq configuration syntax."""
    payload = await request.json()
    return services_dnsmasq_views.test_dnsmasq_config(payload)


@router.get("/services/status", response_class=HTMLResponse)
def services_status(request: Request) -> HTMLResponse:
    """Render the Services / Status page."""
    return services_status_views.render_status(request)


@router.get("/services/dnsmasq", response_class=HTMLResponse)
def services_dnsmasq(request: Request) -> HTMLResponse:
    """Render the Dnsmasq service page."""
    return services_dnsmasq_views.render_dnsmasq(request)


@router.get("/services/proxy", response_class=HTMLResponse)
def services_proxy(request: Request) -> HTMLResponse:
    """Render the Proxy service page."""
    return services_proxy_views.render_proxy(request)
