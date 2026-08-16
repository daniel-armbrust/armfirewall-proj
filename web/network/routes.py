from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from web.network import kernel_params as kernel_params_views
from web.network import neighbor_table as neighbor_table_views
from web.network import policy_routing as policy_routing_views
from web.services.routingprotocols import api as routing_protocols_api
from web.services.routingprotocols import views as routing_protocols_views


router = APIRouter()


@router.get("/api/network/policy-routing")
def api_policy_routing() -> dict[str, Any]:
    """Return persisted policy routing tables, routes, and rules."""
    return policy_routing_views.get_policy_routing()


@router.get("/api/network/policy-routing/work-requests")
def api_policy_routing_work_requests() -> dict[str, Any]:
    """Return recent work requests for policy routing."""
    return policy_routing_views.get_policy_work_requests()


@router.get("/api/network/neighbor-table")
def api_neighbor_table() -> dict[str, Any]:
    """Return the latest persisted neighbor-table snapshot."""
    return neighbor_table_views.get_neighbor_table()


@router.get("/api/network/kernel-params")
def api_kernel_params() -> dict[str, Any]:
    """Return global kernel parameters collected from /proc/sys."""
    return kernel_params_views.get_kernel_params()


@router.put("/api/network/kernel-params/current-value")
async def api_update_kernel_param_current_value(request: Request) -> dict[str, Any]:
    """Update the runtime value for one allowed global kernel parameter."""
    payload = await request.json()
    return kernel_params_views.update_kernel_param_current_value(payload)


@router.get("/api/network/routing-protocols/bird/global-settings")
def api_bird_global_settings() -> dict[str, Any]:
    """Return BIRD global daemon settings."""
    return routing_protocols_api.get_global_settings()


@router.put("/api/network/routing-protocols/bird/global-settings")
async def api_save_bird_global_settings(request: Request) -> dict[str, Any]:
    """Save BIRD global daemon settings."""
    payload = await request.json()
    return routing_protocols_api.save_global_settings(payload)


@router.get("/api/network/routing-protocols/bird/logs")
def api_bird_logs() -> dict[str, Any]:
    """Return recent BIRD daemon logs."""
    return routing_protocols_api.read_bird_logs()


@router.get("/api/network/routing-protocols/bird/diagnostics")
def api_bird_diagnostics() -> dict[str, Any]:
    """Return latest BIRD diagnostics collected from bird.db."""
    return routing_protocols_api.get_bird_diagnostics()


@router.get("/api/network/routing-protocols/bird/rip-diagnostics")
def api_bird_rip_diagnostics() -> dict[str, Any]:
    """Return latest BIRD RIP diagnostics collected from bird.db."""
    return routing_protocols_api.get_rip_diagnostics()


@router.get("/api/network/routing-protocols/bird/rip-settings")
def api_bird_rip_settings() -> dict[str, Any]:
    """Return BIRD RIP protocol settings."""
    return routing_protocols_api.get_rip_settings()


@router.put("/api/network/routing-protocols/bird/rip-settings")
async def api_save_bird_rip_settings(request: Request) -> dict[str, Any]:
    """Save BIRD RIP protocol settings."""
    payload = await request.json()
    return routing_protocols_api.save_rip_settings(payload)




@router.get("/api/network/routing-protocols/bird/bgp-settings")
def api_bird_bgp_settings(instance_id: Optional[int] = None) -> dict[str, Any]:
    """Return BIRD BGP protocol settings."""
    return routing_protocols_api.get_bgp_settings(instance_id)


@router.post("/api/network/routing-protocols/bird/bgp-settings")
async def api_add_bird_bgp_settings(request: Request) -> dict[str, Any]:
    """Create one BIRD BGP protocol instance."""
    payload = await request.json()
    return routing_protocols_api.add_bgp_settings(payload)


@router.put("/api/network/routing-protocols/bird/bgp-settings/{instance_id}")
async def api_save_bird_bgp_settings(instance_id: int, request: Request) -> dict[str, Any]:
    """Update one BIRD BGP protocol instance."""
    payload = await request.json()
    return routing_protocols_api.save_bgp_settings(payload, instance_id)


@router.delete("/api/network/routing-protocols/bird/bgp-settings/{instance_id}")
def api_delete_bird_bgp_settings(instance_id: int) -> dict[str, Any]:
    """Delete one BIRD BGP protocol instance."""
    return routing_protocols_api.delete_bgp_settings(instance_id)


@router.post("/api/network/policy-routing/tables")
async def api_create_policy_routing_table(request: Request) -> dict[str, Any]:
    """Create a policy routing table entry."""
    payload = await request.json()
    return policy_routing_views.create_routing_table(payload)


@router.post("/api/network/policy-routing/routes")
async def api_create_policy_route(request: Request) -> dict[str, Any]:
    """Create a policy route entry."""
    payload = await request.json()
    return policy_routing_views.create_route(payload)


@router.post("/api/network/policy-routing/rules")
async def api_create_policy_rule(request: Request) -> dict[str, Any]:
    """Create a policy routing rule entry."""
    payload = await request.json()
    return policy_routing_views.create_rule(payload)


@router.put("/api/network/policy-routing/{table_name}/{item_id}/enabled")
async def api_set_policy_routing_enabled(request: Request, table_name: str, item_id: int) -> dict[str, Any]:
    """Enable or disable one policy routing item."""
    payload = await request.json()
    return policy_routing_views.set_enabled(table_name, item_id, payload)


@router.delete("/api/network/policy-routing/{table_name}/{item_id}")
def api_delete_policy_routing_item(table_name: str, item_id: int) -> dict[str, Any]:
    """Mark one policy routing item for deletion."""
    return policy_routing_views.mark_pending_delete(table_name, item_id)


@router.post("/api/network/policy-routing/apply")
def api_apply_policy_routing() -> dict[str, Any]:
    """Queue policy routing changes for application."""
    return policy_routing_views.apply_policy_routing()


@router.get("/network/packet-capture")
def network_packet_capture_redirect() -> RedirectResponse:
    """Redirect the old Network packet capture URL to Tools."""
    return RedirectResponse(url="/tools/packet-capture", status_code=308)


@router.get("/network/neighbor-table", response_class=HTMLResponse)
def network_neighbor_table(request: Request) -> HTMLResponse:
    """Render the neighbor table page."""
    return neighbor_table_views.render_neighbor_table(request)


@router.get("/network/kernel-params", response_class=HTMLResponse)
def network_kernel_params(request: Request) -> HTMLResponse:
    """Render the Network / Kernel Params page."""
    return kernel_params_views.render_kernel_params(request)


@router.get("/network/policy-routing", response_class=HTMLResponse)
def network_policy_routing(request: Request) -> HTMLResponse:
    """Render the policy routing page."""
    return policy_routing_views.render_policy_routing(request)


@router.get("/network/routing-protocols", response_class=HTMLResponse)
def network_routing_protocols(request: Request) -> HTMLResponse:
    """Render the routing protocols page."""
    return routing_protocols_views.render_routing_protocols(request)
