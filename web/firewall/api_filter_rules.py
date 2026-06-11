from __future__ import annotations

from typing import Any, Callable, Optional, TypeVar

from fastapi import HTTPException

from daemons.fwrulesd.filter import rules as filter_core


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
