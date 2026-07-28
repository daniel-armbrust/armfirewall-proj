from __future__ import annotations

from typing import Any, Callable, Optional, TypeVar

from fastapi import HTTPException

from daemons.fwrulesd.mangle import rules as mangle_core


T = TypeVar("T")


def _call_core(callback: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Call mangle core logic and translate domain errors to HTTP errors."""
    try:
        return callback(*args, **kwargs)
    except mangle_core.MangleRuleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def get_mangle_rules() -> dict[str, Any]:
    """Return all persisted IPv4 and IPv6 mangle rules grouped by chain."""
    return _call_core(mangle_core.get_mangle_rules)


def get_mangle_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent work requests for mangle firewall rules."""
    return _call_core(mangle_core.get_mangle_work_requests, limit)


def get_mangle_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Return one persisted mangle rule."""
    return _call_core(mangle_core.get_mangle_rule, family, chain, rule_id)


def create_mangle_rule(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a mangle rule without applying it to the operating system."""
    return _call_core(mangle_core.create_mangle_rule, payload)


def apply_mangle_chain(chain: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Queue only mangle families with pending changes for one chain."""
    return _call_core(mangle_core.apply_mangle_chain, chain, (payload or {}).get("family"))


def set_mangle_rule_enabled(family: str, chain: str, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update the enabled flag for a mangle rule without applying it."""
    return _call_core(mangle_core.set_mangle_rule_enabled, family, chain, rule_id, payload)


def delete_mangle_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Mark an editable mangle rule for deletion on the next Apply."""
    return _call_core(mangle_core.delete_mangle_rule, family, chain, rule_id)
