from __future__ import annotations

import ipaddress
from typing import Any, Callable, Optional, TypeVar

from fastapi import HTTPException

from core import db
from daemons.fwrulesd.filter import rules as filter_core
from daemons.fwrulesd.constants import (
    FAMILY_PROTOCOLS,
    FILTER_CHAIN_TABLES,
    FILTER_FAMILY_DATABASES,
)


T = TypeVar("T")


def _call_core(callback: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Call filter core logic and translate domain errors to HTTP errors."""
    try:
        return callback(*args, **kwargs)
    except filter_core.FilterRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def get_filter_rules() -> dict[str, Any]:
    """Return all persisted filter rules grouped by family and chain."""
    return _call_core(filter_core.get_filter_rules)


def get_filter_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent work requests related to filter rules."""
    return _call_core(filter_core.get_filter_work_requests, limit)


def get_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Return one persisted filter rule."""
    return _call_core(filter_core.get_filter_rule, family, chain, rule_id)


def get_filter_rule_state(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the persisted state of a filter rule matched by its attributes."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The request body must be a JSON object.")

    src_addr = str(payload.get("src_addr") or "").strip()
    dst_addr = str(payload.get("dst_addr") or "").strip()
    src_family = _detect_address_family(src_addr, "src_addr")
    dst_family = _detect_address_family(dst_addr, "dst_addr")

    if src_family != dst_family:
        raise HTTPException(status_code=400, detail="src_addr and dst_addr must use the same IP family.")

    family = src_family
    protocols = _normalize_state_list(payload.get("protocol_name"), "protocol_name")
    normalized_protocols: list[str] = []

    for value in protocols:
        protocol = str(value or "").strip().lower()

        if protocol == "icmp" and family == "IPV6":
            protocol = "icmpv6"
        if protocol not in FAMILY_PROTOCOLS[family]:
            raise HTTPException(status_code=400, detail=f"Unsupported protocol for {family}.")
        if protocol not in normalized_protocols:
            normalized_protocols.append(protocol)

    src_ports = _normalize_state_ports(payload.get("src_port"), "src_port")
    dst_ports = _normalize_state_ports(payload.get("dst_port"), "dst_port")
    protocol_placeholders = ", ".join("?" for _ in normalized_protocols)
    src_port_placeholders = ", ".join("?" for _ in src_ports)
    dst_port_placeholders = ", ".join("?" for _ in dst_ports)

    query = f"""
        SELECT protocol_name, src_addr, src_port, dst_addr, dst_port,
               action, protected, enabled, created_at, updated_at
        FROM {{table}}
        WHERE protocol_name IN ({protocol_placeholders})
          AND src_addr = ?
          AND src_port IN ({src_port_placeholders})
          AND dst_addr = ?
          AND dst_port IN ({dst_port_placeholders})
        ORDER BY rule_order, id
    """

    params = (*normalized_protocols, src_addr, *src_ports, dst_addr, *dst_ports)
    matches: list[Any] = []

    with db.connection(FILTER_FAMILY_DATABASES[family]) as conn:
        for table in FILTER_CHAIN_TABLES.values():
            matches.extend(db.execute_on(conn, query.format(table=table), params).fetchall())

    if not matches:
        raise HTTPException(status_code=404, detail="Filter rule not found.")

    row = matches[0]
    
    return {
        "protocol_name": normalized_protocols,
        "src_addr": src_addr,
        "src_port": [str(value) for value in src_ports],
        "dst_addr": dst_addr,
        "dst_port": [str(value) for value in dst_ports],
        "action": str(row["action"]),
        "protected": bool(int(row["protected"])),
        "enabled": bool(int(row["enabled"])),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _normalize_state_list(value: Any, field_name: str) -> list[Any]:
    """Validate a non-empty list supplied as a rule-state criterion."""
    if not isinstance(value, list) or not value:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a non-empty list.")
    return value


def _normalize_state_ports(value: Any, field_name: str) -> list[int]:
    """Normalize and validate source or destination ports."""
    ports: list[int] = []
    for raw_value in _normalize_state_list(value, field_name):
        try:
            port = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{field_name} must contain valid port numbers.") from exc
        if not 0 <= port <= 65535:
            raise HTTPException(status_code=400, detail=f"{field_name} must contain ports between 0 and 65535.")
        if port not in ports:
            ports.append(port)
    return ports


def _detect_address_family(value: Any, field_name: str) -> str:
    """Return IPV4 or IPV6 for an address or network value."""
    rendered = str(value or "").strip()
    if not rendered:
        raise HTTPException(status_code=400, detail=f"{field_name} is required.")
    try:
        address = ipaddress.ip_address(rendered)
    except ValueError:
        try:
            address = ipaddress.ip_network(rendered, strict=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{field_name} must be a valid IPv4 or IPv6 address.") from exc
    return "IPV4" if address.version == 4 else "IPV6"


def create_filter_rule(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a filter rule without applying it to the operating system."""
    return _call_core(filter_core.create_filter_rule, payload)


def update_filter_rule(
    family: str,
    chain: str,
    rule_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Update an editable filter rule without applying it to the operating system."""
    return _call_core(
        filter_core.update_filter_rule,
        family,
        chain,
        rule_id,
        payload,
    )


def apply_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Reject per-rule application so only the chain Apply button can run."""
    return _call_core(filter_core.apply_filter_rule, family, chain, rule_id)


def apply_filter_chain(
    chain: str,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Queue only filter families with pending changes for one chain."""
    return _call_core(filter_core.apply_filter_chain, chain, (payload or {}).get("family"))


def set_filter_chain_policy(chain: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a filter chain policy for IPv4 and IPv6 without applying it."""
    return _call_core(filter_core.set_filter_chain_policy, chain, payload)


def set_filter_rule_enabled(
    family: str,
    chain: str,
    rule_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Update the enabled flag for a filter rule without applying it."""
    return _call_core(
        filter_core.set_filter_rule_enabled,
        family,
        chain,
        rule_id,
        payload,
    )


def delete_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Mark an editable filter rule for deletion on the next Apply."""
    return _call_core(filter_core.delete_filter_rule, family, chain, rule_id)
