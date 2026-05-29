from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.firewall import api_filter_rules as firewall_filter_api
from web.firewall import api_mangle_rules as firewall_mangle_api
from web.firewall import api_nat_rules as firewall_nat_api
from web.firewall import view_filter_rules as firewall_filter_views
from web.firewall import view_mangle_rules as firewall_mangle_views
from web.firewall import view_nat_rules as firewall_nat_views


router = APIRouter()


@router.get("/api/firewall/filter-rules")
def api_firewall_filter_rules() -> dict[str, Any]:
    """Return persisted IPv4 and IPv6 filter rules."""
    return firewall_filter_api.get_filter_rules()


@router.get("/api/firewall/filter-rules/work-requests")
def api_firewall_filter_work_requests() -> dict[str, Any]:
    """Return recent work requests for firewall filter rules."""
    return firewall_filter_api.get_filter_work_requests()


@router.get("/api/firewall/nat-rules")
def api_firewall_nat_rules() -> dict[str, Any]:
    """Return persisted IPv4 and IPv6 NAT rules."""
    return firewall_nat_api.get_nat_rules()


@router.get("/api/firewall/nat-rules/work-requests")
def api_firewall_nat_work_requests() -> dict[str, Any]:
    """Return recent work requests for firewall NAT rules."""
    return firewall_nat_api.get_nat_work_requests()


@router.get("/api/firewall/mangle-rules")
def api_firewall_mangle_rules() -> dict[str, Any]:
    """Return persisted IPv4 and IPv6 mangle rules."""
    return firewall_mangle_api.get_mangle_rules()


@router.get("/api/firewall/mangle-rules/work-requests")
def api_firewall_mangle_work_requests() -> dict[str, Any]:
    """Return recent work requests for firewall mangle rules."""
    return firewall_mangle_api.get_mangle_work_requests()


@router.post("/api/firewall/filter-rules")
async def api_create_firewall_filter_rule(request: Request) -> dict[str, Any]:
    """Create a filter rule and queue it for application."""
    payload = await request.json()
    return firewall_filter_api.create_filter_rule(payload)


@router.post("/api/firewall/nat-rules")
async def api_create_firewall_nat_rule(request: Request) -> dict[str, Any]:
    """Create a NAT rule and queue it for application."""
    payload = await request.json()
    return firewall_nat_api.create_nat_rule(payload)


@router.put("/api/firewall/nat-rules/{family}/{chain}/{rule_id}")
async def api_update_firewall_nat_rule(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Update a NAT rule and queue the change."""
    payload = await request.json()
    return firewall_nat_api.update_nat_rule(family, chain, rule_id, payload)


@router.delete("/api/firewall/nat-rules/{family}/{chain}/{rule_id}")
def api_delete_firewall_nat_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Delete a NAT rule and queue its removal."""
    return firewall_nat_api.delete_nat_rule(family, chain, rule_id)


@router.post("/api/firewall/mangle-rules")
async def api_create_firewall_mangle_rule(request: Request) -> dict[str, Any]:
    """Create a mangle rule and queue it for application."""
    payload = await request.json()
    return firewall_mangle_api.create_mangle_rule(payload)


@router.put("/api/firewall/filter-rules/{family}/{chain}/{rule_id}")
async def api_update_firewall_filter_rule(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Update a filter rule and queue the change."""
    payload = await request.json()
    return firewall_filter_api.update_filter_rule(family, chain, rule_id, payload)


@router.delete("/api/firewall/filter-rules/{family}/{chain}/{rule_id}")
def api_delete_firewall_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Delete a filter rule and queue its removal."""
    return firewall_filter_api.delete_filter_rule(family, chain, rule_id)


@router.delete("/api/firewall/mangle-rules/{family}/{chain}/{rule_id}")
def api_delete_firewall_mangle_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Delete a mangle rule and queue its removal."""
    return firewall_mangle_api.delete_mangle_rule(family, chain, rule_id)


@router.post("/api/firewall/filter-rules/{family}/{chain}/{rule_id}/apply")
def api_apply_firewall_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Queue an existing filter rule for application."""
    return firewall_filter_api.apply_filter_rule(family, chain, rule_id)


@router.post("/api/firewall/filter-rules/{chain}/apply")
async def api_apply_firewall_filter_chain(request: Request, chain: str) -> dict[str, Any]:
    """Queue enabled filter rules for one chain and optional family."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - empty request body keeps old behavior.
        payload = {}
    return firewall_filter_api.apply_filter_chain(chain, payload)


@router.put("/api/firewall/filter-rules/{chain}/policy")
async def api_set_firewall_filter_chain_policy(request: Request, chain: str) -> dict[str, Any]:
    """Persist the selected filter chain policy."""
    payload = await request.json()
    return firewall_filter_api.set_filter_chain_policy(chain, payload)


@router.post("/api/firewall/nat-rules/{chain}/apply")
async def api_apply_firewall_nat_chain(request: Request, chain: str) -> dict[str, Any]:
    """Queue enabled NAT rules for one chain and optional family."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - empty request body keeps old behavior.
        payload = {}
    return firewall_nat_api.apply_nat_chain(chain, payload)


@router.post("/api/firewall/mangle-rules/{chain}/apply")
async def api_apply_firewall_mangle_chain(request: Request, chain: str) -> dict[str, Any]:
    """Queue enabled mangle rules for one chain and optional family."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - empty request body keeps old behavior.
        payload = {}
    return firewall_mangle_api.apply_mangle_chain(chain, payload)


@router.put("/api/firewall/filter-rules/{family}/{chain}/{rule_id}/enabled")
async def api_set_firewall_filter_rule_enabled(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Enable or disable one filter rule and queue the change."""
    payload = await request.json()
    return firewall_filter_api.set_filter_rule_enabled(family, chain, rule_id, payload)


@router.put("/api/firewall/nat-rules/{family}/{chain}/{rule_id}/enabled")
async def api_set_firewall_nat_rule_enabled(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Enable or disable one NAT rule and queue the change."""
    payload = await request.json()
    return firewall_nat_api.set_nat_rule_enabled(family, chain, rule_id, payload)


@router.put("/api/firewall/mangle-rules/{family}/{chain}/{rule_id}/enabled")
async def api_set_firewall_mangle_rule_enabled(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Enable or disable one mangle rule and queue the change."""
    payload = await request.json()
    return firewall_mangle_api.set_mangle_rule_enabled(family, chain, rule_id, payload)


@router.get("/firewall/filter-rules", response_class=HTMLResponse)
def firewall_filter_rules(request: Request) -> HTMLResponse:
    """Render the firewall filter rules page."""
    return firewall_filter_views.render_filter_rules(request)


@router.get("/firewall/nat-rules", response_class=HTMLResponse)
def firewall_nat_rules(request: Request) -> HTMLResponse:
    """Render the firewall NAT rules page."""
    return firewall_nat_views.render_nat_rules(request)


@router.get("/firewall/mangle-rules", response_class=HTMLResponse)
def firewall_mangle_rules(request: Request) -> HTMLResponse:
    """Render the firewall mangle rules page."""
    return firewall_mangle_views.render_mangle_rules(request)
