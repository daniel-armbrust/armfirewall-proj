from __future__ import annotations

from typing import Any, Callable, TypeVar

from fastapi import HTTPException

from daemons.fwrulesd.nat import rules as nat_core


T = TypeVar("T")


def _call_core(callback: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Call NAT core logic and translate domain errors to HTTP errors."""
    try:
        return callback(*args, **kwargs)
    except nat_core.NatRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def get_nat_rules() -> dict[str, Any]:
    """Return all persisted IPv4 and IPv6 NAT rules grouped by chain."""
    return _call_core(nat_core.get_nat_rules)


def get_nat_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent work requests for NAT firewall rules."""
    return _call_core(nat_core.get_nat_work_requests, limit)


def get_nat_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Return one persisted NAT rule."""
    return _call_core(nat_core.get_nat_rule, family, chain, rule_id)


def create_nat_rule(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a NAT rule without applying it to the operating system."""
    return _call_core(nat_core.create_nat_rule, payload)


def update_nat_rule(family: str, chain: str, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update an editable NAT rule without applying it to the operating system."""
    return _call_core(nat_core.update_nat_rule, family, chain, rule_id, payload)


def apply_nat_chain(chain: str) -> dict[str, Any]:
    """Queue only NAT families with pending changes for one chain."""
    return _call_core(nat_core.apply_nat_chain, chain)


def set_nat_rule_enabled(family: str, chain: str, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update the enabled flag for a NAT rule without applying it."""
    return _call_core(nat_core.set_nat_rule_enabled, family, chain, rule_id, payload)


def delete_nat_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Mark an editable NAT rule for deletion on the next Apply."""
    return _call_core(nat_core.delete_nat_rule, family, chain, rule_id)
