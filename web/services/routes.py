from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.services.dnsmasq import api as services_dnsmasq_api
from web.services.dnsmasq import views as services_dnsmasq_views
from web.services.adguardhome import api as services_adguardhome_api
from web.services.adguardhome import views as services_adguardhome_views
from web.services.libreswan import api as services_libreswan_api
from web.services.libreswan import views as services_libreswan_views
from web.services.linkfailover import api as services_linkfailover_api
from web.services.linkfailover import views as services_linkfailover_views
from web.services.squid import views as services_squid_views
from web.services import api as services_api
from web.services import views as services_views
from web.workrequests import routes as workrequests_routes


router = APIRouter()


def post_service_work_request(service_request: dict[str, Any]) -> dict[str, Any]:
    """Queue a service request through the Work Requests API."""
    queue_result = workrequests_routes.api_queue_service_work_request(
        {
            "action": service_request["action"],
            "category_name": service_request["category_name"],
            "payload": service_request["payload"],
        }
    )

    return {
        "name": service_request["name"],
        "action": service_request["action"],
        "status": queue_result["status"],
        "work_request_id": queue_result["work_request_id"],
    }


@router.get("/api/services/status")
def api_services_status() -> dict[str, Any]:
    """Return ArmFirewall supervisord service statuses."""
    return services_api.services_status()


@router.get("/api/services/status/work-requests")
def api_services_status_work_requests() -> dict[str, Any]:
    """Return ArmFirewall service management work requests."""
    return workrequests_routes.api_service_work_requests()


@router.post("/api/services/status/{service_name}/action")
def api_control_service(service_name: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Control one non-protected ArmFirewall supervisord service."""
    try:
        service_request = services_api.control_service(service_name, str(payload.get("action", "")))
        return post_service_work_request(service_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/services/status/{service_name}/install")
def api_install_optional_service(service_name: str) -> dict[str, Any]:
    """Queue installation for one optional ArmFirewall service."""
    try:
        service_request = services_api.install_optional_service(service_name)
        return post_service_work_request(service_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/services/status/{service_name}/uninstall")
def api_uninstall_optional_service(service_name: str) -> dict[str, Any]:
    """Queue removal for one optional ArmFirewall service."""
    try:
        service_request = services_api.uninstall_optional_service(service_name)
        return post_service_work_request(service_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/services/dnsmasq")
def api_dnsmasq_config() -> dict[str, Any]:
    """Return dnsmasq configuration and service status."""
    return services_dnsmasq_api.get_dnsmasq_config()


@router.get("/api/services/adguardhome")
def api_adguardhome_config() -> dict[str, Any]:
    """Return AdGuard Home configuration and service status."""
    return services_adguardhome_api.get_config()


@router.put("/api/services/adguardhome")
async def api_save_adguardhome_config(request: Request) -> dict[str, Any]:
    """Persist AdGuard Home global settings from the GUI."""
    return services_adguardhome_api.update_settings(await request.json())


@router.post("/api/services/adguardhome/filters")
async def api_add_adguardhome_filter(request: Request) -> dict[str, Any]:
    """Add one AdGuard Home remote filter source."""
    return services_adguardhome_api.add_filter(await request.json())


@router.delete("/api/services/adguardhome/filters/{filter_id}")
def api_delete_adguardhome_filter(filter_id: int) -> dict[str, Any]:
    """Remove one AdGuard Home remote filter source."""
    return services_adguardhome_api.delete_filter(filter_id)


@router.get("/api/services/dnsmasq/work-requests")
def api_dnsmasq_work_requests() -> dict[str, Any]:
    """Return Dnsmasq configuration work requests."""
    return services_dnsmasq_api.get_dnsmasq_work_requests()


@router.get("/api/services/link-failover")
def api_linkfailover_config() -> dict[str, Any]:
    """Return Link Failover configuration and status."""
    return services_linkfailover_api.get_config()


@router.get("/api/services/link-failover/work-requests")
def api_linkfailover_work_requests() -> dict[str, Any]:
    """Return Link Failover service work requests."""
    return services_linkfailover_api.get_service_work_requests()


@router.get("/api/services/libreswan")
def api_libreswan_config() -> dict[str, Any]:
    """Return Libreswan connections and service status."""
    return services_libreswan_api.list_connections()


@router.get("/api/services/libreswan/logs")
def api_libreswan_logs(limit: int = 400) -> dict[str, Any]:
    """Return Libreswan process logs."""
    return services_libreswan_api.list_logs(limit=limit)


@router.get("/api/services/libreswan/work-requests")
def api_libreswan_work_requests() -> dict[str, Any]:
    """Return Libreswan configuration work requests."""
    return services_libreswan_api.get_libreswan_work_requests()


@router.put("/api/services/link-failover/settings")
async def api_save_linkfailover_settings(request: Request) -> dict[str, Any]:
    """Save Link Failover global settings."""
    payload = await request.json()
    return services_linkfailover_api.update_settings(payload)


@router.post("/api/services/link-failover/links")
async def api_create_linkfailover_link(request: Request) -> dict[str, Any]:
    """Create one Link Failover link."""
    payload = await request.json()
    return services_linkfailover_api.create_link(payload)


@router.put("/api/services/link-failover/links/{link_id}")
async def api_update_linkfailover_link(link_id: int, request: Request) -> dict[str, Any]:
    """Update one Link Failover link."""
    payload = await request.json()
    return services_linkfailover_api.update_link(link_id, payload)


@router.delete("/api/services/link-failover/links/{link_id}")
def api_delete_linkfailover_link(link_id: int) -> dict[str, Any]:
    """Delete one Link Failover link."""
    return services_linkfailover_api.delete_link(link_id)


@router.post("/api/services/libreswan/connections")
async def api_create_libreswan_connection(request: Request) -> dict[str, Any]:
    """Create one Libreswan connection."""
    payload = await request.json()
    return services_libreswan_api.create_connection(payload)


@router.put("/api/services/libreswan/connections/{connection_id}")
async def api_update_libreswan_connection(connection_id: int, request: Request) -> dict[str, Any]:
    """Update one Libreswan connection."""
    payload = await request.json()
    return services_libreswan_api.update_connection(connection_id, payload)


@router.put("/api/services/libreswan/connections/{connection_id}/enabled")
async def api_set_libreswan_connection_enabled(connection_id: int, request: Request) -> dict[str, Any]:
    """Enable or disable one Libreswan connection."""
    payload = await request.json()
    return services_libreswan_api.set_connection_enabled(connection_id, bool(payload.get("enabled")))


@router.delete("/api/services/libreswan/connections/{connection_id}")
def api_delete_libreswan_connection(connection_id: int) -> dict[str, Any]:
    """Delete one Libreswan connection."""
    return services_libreswan_api.delete_connection(connection_id)


@router.put("/api/services/dnsmasq")
async def api_save_dnsmasq_config(request: Request) -> dict[str, Any]:
    """Save dnsmasq configuration from the GUI."""
    payload = await request.json()
    return services_dnsmasq_api.save_dnsmasq_config(payload)


@router.post("/api/services/dnsmasq/test")
async def api_test_dnsmasq_config(request: Request) -> dict[str, Any]:
    """Validate dnsmasq configuration syntax."""
    payload = await request.json()
    return services_dnsmasq_api.test_dnsmasq_config(payload)


@router.get("/services/status", response_class=HTMLResponse)
def services_status(request: Request) -> HTMLResponse:
    """Render the Services / Status page."""
    return services_views.render_status(request)


@router.get("/services/dnsmasq", response_class=HTMLResponse)
def services_dnsmasq(request: Request) -> HTMLResponse:
    """Render the Dnsmasq service page."""
    return services_dnsmasq_views.render_dnsmasq(request)


@router.get("/services/adguard", response_class=HTMLResponse)
def services_adguardhome(request: Request) -> HTMLResponse:
    """Render the AdGuard Home service page."""
    return services_adguardhome_views.render_adguardhome(request)


@router.get("/services/libreswan", response_class=HTMLResponse)
def services_libreswan(request: Request) -> HTMLResponse:
    """Render the Libreswan service page."""
    return services_libreswan_views.render_libreswan(request)


@router.get("/services/link-failover", response_class=HTMLResponse)
def services_linkfailover(request: Request) -> HTMLResponse:
    """Render the Link Failover service page."""
    return services_linkfailover_views.render_linkfailover(request)


@router.get("/services/squid", response_class=HTMLResponse)
def services_squid(request: Request) -> HTMLResponse:
    """Render the Squid service page."""
    return services_squid_views.render_squid(request)
