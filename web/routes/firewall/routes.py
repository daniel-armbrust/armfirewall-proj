from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.firewall import filter_rules as firewall_filter_views
from web.firewall import mangle_rules as firewall_mangle_views
from web.firewall import nat_rules as firewall_nat_views


router = APIRouter()


@router.get("/api/firewall/filter-rules")
def api_firewall_filter_rules() -> dict[str, Any]:
    """Return persisted IPv4 and IPv6 filter rules."""
    return firewall_filter_views.get_filter_rules()


@router.get("/api/firewall/filter-rules/work-requests")
def api_firewall_filter_work_requests() -> dict[str, Any]:
    """Return recent work requests for firewall filter rules."""
    return firewall_filter_views.get_filter_work_requests()


@router.get("/api/firewall/nat-rules")
def api_firewall_nat_rules() -> dict[str, Any]:
    """Return persisted IPv4 and IPv6 NAT rules."""
    return firewall_nat_views.get_nat_rules()


@router.get("/api/firewall/nat-rules/work-requests")
def api_firewall_nat_work_requests() -> dict[str, Any]:
    """Return recent work requests for firewall NAT rules."""
    return firewall_nat_views.get_nat_work_requests()


@router.get("/api/firewall/mangle-rules")
def api_firewall_mangle_rules() -> dict[str, Any]:
    """Return persisted IPv4 and IPv6 mangle rules."""
    return firewall_mangle_views.get_mangle_rules()


@router.get("/api/firewall/mangle-rules/work-requests")
def api_firewall_mangle_work_requests() -> dict[str, Any]:
    """Return recent work requests for firewall mangle rules."""
    return firewall_mangle_views.get_mangle_work_requests()


@router.post("/api/firewall/filter-rules")
async def api_create_firewall_filter_rule(request: Request) -> dict[str, Any]:
    """Create a filter rule and queue it for application."""
    payload = await request.json()
    return firewall_filter_views.create_filter_rule(payload)


@router.post("/api/firewall/nat-rules")
async def api_create_firewall_nat_rule(request: Request) -> dict[str, Any]:
    """Create a NAT rule and queue it for application."""
    payload = await request.json()
    return firewall_nat_views.create_nat_rule(payload)


@router.put("/api/firewall/nat-rules/{family}/{chain}/{rule_id}")
async def api_update_firewall_nat_rule(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Update a NAT rule and queue the change."""
    payload = await request.json()
    return firewall_nat_views.update_nat_rule(family, chain, rule_id, payload)


@router.delete("/api/firewall/nat-rules/{family}/{chain}/{rule_id}")
def api_delete_firewall_nat_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Delete a NAT rule and queue its removal."""
    return firewall_nat_views.delete_nat_rule(family, chain, rule_id)


@router.post("/api/firewall/mangle-rules")
async def api_create_firewall_mangle_rule(request: Request) -> dict[str, Any]:
    """Create a mangle rule and queue it for application."""
    payload = await request.json()
    return firewall_mangle_views.create_mangle_rule(payload)


@router.put("/api/firewall/filter-rules/{family}/{chain}/{rule_id}")
async def api_update_firewall_filter_rule(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Update a filter rule and queue the change."""
    payload = await request.json()
    return firewall_filter_views.update_filter_rule(family, chain, rule_id, payload)


@router.delete("/api/firewall/filter-rules/{family}/{chain}/{rule_id}")
def api_delete_firewall_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Delete a filter rule and queue its removal."""
    return firewall_filter_views.delete_filter_rule(family, chain, rule_id)


@router.delete("/api/firewall/mangle-rules/{family}/{chain}/{rule_id}")
def api_delete_firewall_mangle_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Delete a mangle rule and queue its removal."""
    return firewall_mangle_views.delete_mangle_rule(family, chain, rule_id)


@router.post("/api/firewall/filter-rules/{family}/{chain}/{rule_id}/apply")
def api_apply_firewall_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Queue an existing filter rule for application."""
    return firewall_filter_views.apply_filter_rule(family, chain, rule_id)


@router.post("/api/firewall/filter-rules/{chain}/apply")
def api_apply_firewall_filter_chain(chain: str) -> dict[str, Any]:
    """Queue enabled IPv4 and IPv6 filter rules for one chain."""
    return firewall_filter_views.apply_filter_chain(chain)


@router.post("/api/firewall/nat-rules/{chain}/apply")
def api_apply_firewall_nat_chain(chain: str) -> dict[str, Any]:
    """Queue enabled IPv4 and IPv6 NAT rules for one chain."""
    return firewall_nat_views.apply_nat_chain(chain)


@router.post("/api/firewall/mangle-rules/{chain}/apply")
def api_apply_firewall_mangle_chain(chain: str) -> dict[str, Any]:
    """Queue enabled IPv4 and IPv6 mangle rules for one chain."""
    return firewall_mangle_views.apply_mangle_chain(chain)


@router.put("/api/firewall/filter-rules/{family}/{chain}/{rule_id}/enabled")
async def api_set_firewall_filter_rule_enabled(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Enable or disable one filter rule and queue the change."""
    payload = await request.json()
    return firewall_filter_views.set_filter_rule_enabled(family, chain, rule_id, payload)


@router.put("/api/firewall/nat-rules/{family}/{chain}/{rule_id}/enabled")
async def api_set_firewall_nat_rule_enabled(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Enable or disable one NAT rule and queue the change."""
    payload = await request.json()
    return firewall_nat_views.set_nat_rule_enabled(family, chain, rule_id, payload)


@router.put("/api/firewall/mangle-rules/{family}/{chain}/{rule_id}/enabled")
async def api_set_firewall_mangle_rule_enabled(
    request: Request,
    family: str,
    chain: str,
    rule_id: int,
) -> dict[str, Any]:
    """Enable or disable one mangle rule and queue the change."""
    payload = await request.json()
    return firewall_mangle_views.set_mangle_rule_enabled(family, chain, rule_id, payload)


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
