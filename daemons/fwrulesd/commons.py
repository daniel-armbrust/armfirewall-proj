"""Shared iptables naming helpers used by firewall rule executors."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from core import db
from core.constants import WORK_REQUEST_DB_PATH

from .constants import FAMILY_PROTOCOLS


def command_name(family: str) -> str:
    """Return the iptables command for one address family."""
    return "ip6tables" if family == "IPV6" else "iptables"


class FirewallRuleError(ValueError):
    """Firewall rule failure with an HTTP-friendly status code for callers."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_family(value: Any, *, family_databases: Mapping[str, Any], error_cls: type[FirewallRuleError]) -> str:
    """Normalize and validate a firewall address family."""
    family = str(value or "IPV4").strip().upper()

    if family not in family_databases:
        raise error_cls("family must be IPV4 or IPV6.", 400)

    return family


def normalize_chain(
    value: Any,
    *,
    chain_tables: Mapping[str, str],
    default: str,
    error_message: str,
    error_cls: type[FirewallRuleError],
) -> str:
    """Normalize and validate a firewall chain name."""
    chain = str(value or default).strip().upper()

    if chain not in chain_tables:
        raise error_cls(error_message, 400)

    return chain


def normalize_protocol(family: str, value: Any, *, error_cls: type[FirewallRuleError]) -> str:
    """Normalize and validate a protocol for one address family."""
    protocol = str(value or "tcp").strip().lower()

    if protocol == "icmp" and family == "IPV6":
        protocol = "icmpv6"

    if protocol not in FAMILY_PROTOCOLS[family]:
        raise error_cls(f"Unsupported protocol for {family}.", 400)

    return protocol


def normalize_enabled(value: Any) -> int:
    """Convert an enabled value to a SQLite flag."""
    return 1 if str(value).lower() in {"1", "true", "yes", "on"} else 0


def default_address(family: str) -> str:
    """Return the wildcard source or destination address for one family."""
    return "::/0" if family == "IPV6" else "0.0.0.0/0"


def optional_int(value: Any, *, error_cls: type[FirewallRuleError]) -> int | None:
    """Convert an optional numeric value to int."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise error_cls(f"Invalid integer value: {value}", 400) from exc


def next_rule_order(conn: db.Connection, table: str) -> int:
    """Return the next rule order for one chain table."""
    row = db.fetch_one_on(conn, f"SELECT COALESCE(MAX(rule_order), 0) + 1 AS next_order FROM {table}")

    return int(row["next_order"] if row is not None else 1)


def ensure_pending_delete_column(conn: db.Connection, table: str) -> None:
    """Add compatibility columns required by rule tables when needed."""
    columns = {str(row["name"]) for row in db.execute_on(conn, f"PRAGMA table_info({table})").fetchall()}

    if "pending_delete" not in columns:
        db.execute_on(conn, f"ALTER TABLE {table} ADD COLUMN pending_delete INTEGER NOT NULL DEFAULT 0")
    if "rule_source" not in columns:
        db.execute_on(conn, f"ALTER TABLE {table} ADD COLUMN rule_source TEXT NOT NULL DEFAULT 'system'")
    db.execute_on(
        conn,
        f"UPDATE {table} SET rule_source = CASE WHEN protected = 1 THEN 'system' ELSE 'user' END "
        "WHERE rule_source IS NULL OR rule_source = ''",
    )


def row_to_rule(family: str, chain: str, row: Any, *, chain_tables: Mapping[str, str]) -> dict[str, Any]:
    """Convert a SQLite rule row into API data."""
    data = db.row_to_dict(row)
    data["family"] = family
    data["chain"] = chain
    data["table_name"] = chain_tables[chain]
    data["enabled_label"] = "enabled" if int(data["enabled"]) == 1 else "disabled"
    data["protected_label"] = "protected" if int(data["protected"]) == 1 else "editable"
    rule_source = str(data.get("rule_source") or ("system" if int(data["protected"]) == 1 else "user")).strip().lower()
    if rule_source not in {"system", "user"}:
        rule_source = "system" if int(data["protected"]) == 1 else "user"
    data["rule_source"] = rule_source
    data["user_defined"] = 1 if rule_source == "user" else 0
    data["rule_source_label"] = "user defined" if rule_source == "user" else "system"

    return data


def last_successful_apply_times(category_like: str) -> dict[str, str]:
    """Return the last successful apply timestamp by work request category."""
    query = """
        SELECT category_name, MAX(updated_at) AS applied_at
        FROM work_requests
        WHERE category_name LIKE ?
          AND action_name = 'apply'
          AND status = 'success'
        GROUP BY category_name
    """
    with db.connection(WORK_REQUEST_DB_PATH) as conn:
        rows = db.fetch_all_on(conn, query, (category_like,))

    return {
        str(row["category_name"]): str(row["applied_at"])
        for row in rows
        if row.get("applied_at") is not None
    }


def mark_apply_state(
    rules: list[dict[str, Any]],
    *,
    category_prefix: str,
    apply_times_callback: Callable[[], dict[str, str]],
) -> None:
    """Mark rules as active only when saved before the last Apply."""
    apply_times = apply_times_callback()

    for rule in rules:
        category_name = f"{category_prefix}.{rule['family']}.{rule['table_name']}"
        applied_at = apply_times.get(category_name)
        is_enabled = int(rule["enabled"]) == 1
        is_protected = int(rule["protected"]) == 1
        is_pending_delete = int(rule.get("pending_delete") or 0) == 1
        is_active = bool(
            is_enabled
            and not is_pending_delete
            and (is_protected or (applied_at and str(rule["updated_at"]) <= applied_at))
        )
        rule["applied"] = 1 if is_active else 0
        rule["apply_state"] = "delete_pending" if is_pending_delete else "active" if is_active else "pending" if is_enabled else "disabled"
