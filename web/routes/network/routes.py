from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from web.network import kernel_params as kernel_params_views
from web.network import neighbor_table as neighbor_table_views
from web.network import policy_routing as policy_routing_views


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
    """Return the current operating system neighbor table."""
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
