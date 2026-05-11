from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.services.dnsmasq import dnsmasq as services_dnsmasq_views
from web.services.linkfailover import linkfailover as services_linkfailover_views
from web.services.proxy import proxy as services_proxy_views
from web.services import status as services_status_views


router = APIRouter()


@router.get("/api/services/status")
def api_services_status() -> dict[str, Any]:
    """Return ArmFirewall supervisord service statuses."""
    return services_status_views.services_status()


@router.get("/api/services/status/work-requests")
def api_services_status_work_requests() -> dict[str, Any]:
    """Return ArmFirewall service management work requests."""
    return services_status_views.get_service_work_requests()


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


@router.get("/api/services/dnsmasq/work-requests")
def api_dnsmasq_work_requests() -> dict[str, Any]:
    """Return Dnsmasq configuration work requests."""
    return services_dnsmasq_views.get_dnsmasq_work_requests()


@router.get("/api/services/link-failover")
def api_linkfailover_config() -> dict[str, Any]:
    """Return Link Failover configuration and status."""
    return services_linkfailover_views.get_config()


@router.get("/api/services/link-failover/work-requests")
def api_linkfailover_work_requests() -> dict[str, Any]:
    """Return Link Failover service work requests."""
    return services_linkfailover_views.get_service_work_requests()


@router.put("/api/services/link-failover/settings")
async def api_save_linkfailover_settings(request: Request) -> dict[str, Any]:
    """Save Link Failover global settings."""
    payload = await request.json()
    return services_linkfailover_views.update_settings(payload)


@router.post("/api/services/link-failover/links")
async def api_create_linkfailover_link(request: Request) -> dict[str, Any]:
    """Create one Link Failover link."""
    payload = await request.json()
    return services_linkfailover_views.create_link(payload)


@router.put("/api/services/link-failover/links/{link_id}")
async def api_update_linkfailover_link(link_id: int, request: Request) -> dict[str, Any]:
    """Update one Link Failover link."""
    payload = await request.json()
    return services_linkfailover_views.update_link(link_id, payload)


@router.delete("/api/services/link-failover/links/{link_id}")
def api_delete_linkfailover_link(link_id: int) -> dict[str, Any]:
    """Delete one Link Failover link."""
    return services_linkfailover_views.delete_link(link_id)


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


@router.get("/services/link-failover", response_class=HTMLResponse)
def services_linkfailover(request: Request) -> HTMLResponse:
    """Render the Link Failover service page."""
    return services_linkfailover_views.render_linkfailover(request)


@router.get("/services/proxy", response_class=HTMLResponse)
def services_proxy(request: Request) -> HTMLResponse:
    """Render the Proxy service page."""
    return services_proxy_views.render_proxy(request)
