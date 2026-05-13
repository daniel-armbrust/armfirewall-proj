"""Firewall rule work request execution flow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from core import log as logger

from .commands import apply_rule, flush_chain, remove_rule
from .constants import LOG_SOURCE
from .filter import table as filter_table
from .models import FirewallWorkRequest
from .repository import (
    delete_failed_rule,
    fetch_protected_rules,
    purge_pending_delete_rules,
    rules_for_payload,
    table_from_request,
    verify_rule_database,
)


def reconcile_protected_rules() -> int:
    """Reapply any missing protected rule from SQLite."""
    applied = 0

    for category in ("FIREWALL_RULES", "NAT_RULES", "MANGLE_RULES"):
        for family in ("IPV4", "IPV6"):
            rule_args = SimpleNamespace(family=family, target_name=None)

            for rule in fetch_protected_rules(category, family):
                applied += 1 if apply_rule(rule_args, rule) else 0

    return applied


def execute_work_request(args: Any, payload: dict[str, Any]) -> tuple[int, int]:
    """Execute one work request and return applied and removed counts."""
    table = table_from_request(args, payload)
    rules = rules_for_payload(args, payload)
    applied = 0
    removed = 0

    if args.action_name == "apply" and isinstance(payload.get("rule_ids"), list):
        flush_chain(args, table)
        applied += filter_table.apply_payload_filter_policy(args, table, payload)

    for rule in rules:
        try:
            if args.action_name == "remove":
                removed += remove_rule(args, rule)
            elif args.action_name == "change" and int(rule.get("enabled") or 0) == 0:
                removed += remove_rule(args, rule)
            elif args.action_name in {"apply", "change"}:
                applied += 1 if apply_rule(args, rule) else 0
            else:
                raise RuntimeError(f"Unsupported firewall action: {args.action_name}")
        except Exception:
            if args.action_name == "apply" and isinstance(payload.get("rule_ids"), list):
                removed += delete_failed_rule(args, table, rule)
            raise

    if args.action_name == "apply" and isinstance(payload.get("rule_ids"), list):
        removed += purge_pending_delete_rules(args, table, payload)

    if args.action_name == "apply":
        applied += reconcile_protected_rules()
        filter_table.enforce_configured_filter_policies()

    return applied, removed


def run_action(args: FirewallWorkRequest) -> int:
    """Handle one dispatched firewall-related work request."""
    if args.category not in {"FIREWALL_RULES", "NAT_RULES", "MANGLE_RULES"}:
        logger.error(f"Unsupported firewall category: {args.category}", source=LOG_SOURCE)
        return 2

    try:
        verify_rule_database(args.category, args.family)
    except Exception as exc:  # noqa: BLE001 - message is returned to workreqd.
        logger.error(f"Could not connect to rule database: {exc}", source=LOG_SOURCE)
        return 1

    logger.log(
        "Received work request "
        f"id={args.work_request_id} category={args.category_name} action={args.action_name}.",
        source=LOG_SOURCE,
    )

    try:
        applied, removed = execute_work_request(args, args.payload)
    except Exception as exc:  # noqa: BLE001 - message is returned to workreqd.
        logger.error(f"Firewall rule execution failed: {exc}", source=LOG_SOURCE)
        return 1

    logger.log(
        f"Firewall rule execution completed: applied={applied}, removed={removed}.",
        source=LOG_SOURCE,
    )

    return 0
