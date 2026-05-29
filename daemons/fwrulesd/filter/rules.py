from __future__ import annotations

import json
import uuid
from functools import partial
from typing import Any

from core import db
from core.constants import WORK_REQUEST_DB_PATH
from daemons.fwrulesd import commons
from daemons.fwrulesd.constants import (
    FILTER_ACTIONS,
    FILTER_CHAIN_TABLES,
    FILTER_DEFAULT_POLICIES,
    FILTER_FAMILY_DATABASES,
    FILTER_POLICIES,
)
from daemons.fwrulesd.filter.policies import require_filter_chain_policies


class FilterRuleError(commons.FirewallRuleError):
    """Filter rule failure with an HTTP-friendly status code for callers."""


normalize_family = partial(
    commons.normalize_family,
    family_databases=FILTER_FAMILY_DATABASES,
    error_cls=FilterRuleError,
)
normalize_chain = partial(
    commons.normalize_chain,
    chain_tables=FILTER_CHAIN_TABLES,
    default="INPUT",
    error_message="chain must be INPUT, FORWARD, or OUTPUT.",
    error_cls=FilterRuleError,
)
normalize_protocol = partial(commons.normalize_protocol, error_cls=FilterRuleError)
normalize_enabled = commons.normalize_enabled
default_address = commons.default_address
optional_int = partial(commons.optional_int, error_cls=FilterRuleError)
next_rule_order = commons.next_rule_order
ensure_pending_delete_column = commons.ensure_pending_delete_column
row_to_rule = partial(commons.row_to_rule, chain_tables=FILTER_CHAIN_TABLES)
last_successful_apply_times = partial(commons.last_successful_apply_times, "FIREWALL_RULES.%filter_%")
mark_apply_state = partial(
    commons.mark_apply_state,
    category_prefix="FIREWALL_RULES",
    apply_times_callback=last_successful_apply_times,
)


def normalize_action(value: Any) -> str:
    """Normalize and validate a filter action."""
    action = str(value or "ACCEPT").strip().upper()
    if action not in FILTER_ACTIONS:
        raise FilterRuleError("action must be ACCEPT, DROP, or REJECT.", 400)
    return action


def normalize_policy(value: Any) -> str:
    """Normalize and validate a built-in chain policy."""
    policy = str(value or "DROP").strip().upper()
    if policy not in FILTER_POLICIES:
        raise FilterRuleError("policy must be ACCEPT or DROP.", 400)
    return policy


def get_rules_for_table(family: str, chain: str) -> list[dict[str, Any]]:
    """Read enabled and disabled rules from one filter chain table."""
    table = FILTER_CHAIN_TABLES[chain]
    db_path = FILTER_FAMILY_DATABASES[family]

    if chain == "INPUT":
        query = f"""
            SELECT id, rule_order, iface_in, '' AS iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   action, protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            ORDER BY rule_order, id
        """
    elif chain == "FORWARD":
        query = f"""
            SELECT id, rule_order, iface_in, iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   action, protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            ORDER BY rule_order, id
        """
    else:
        query = f"""
            SELECT id, rule_order, '' AS iface_in, iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   action, protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            ORDER BY rule_order, id
        """

    with db.connection(db_path) as conn:
        require_filter_chain_policies(conn)
        ensure_pending_delete_column(conn, table)
        return [row_to_rule(family, chain, row) for row in db.execute_on(conn, query).fetchall()]


def get_filter_policies() -> dict[str, dict[str, Any]]:
    """Return persisted filter policies by chain and family."""
    policies: dict[str, dict[str, Any]] = {chain: {} for chain in FILTER_CHAIN_TABLES}
    for family, db_path in FILTER_FAMILY_DATABASES.items():
        with db.connection(db_path) as conn:
            require_filter_chain_policies(conn)
            rows = db.fetch_all_on(
                conn,
                """
                SELECT chain_name, policy, updated_at
                FROM filter_chain_policies
                ORDER BY chain_name
                """,
            )
        for row in rows:
            chain = str(row["chain_name"])
            policies.setdefault(chain, {})[family] = {
                "policy": str(row["policy"]),
                "updated_at": str(row["updated_at"]),
            }
    return policies


def get_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Return one persisted filter rule or fail when it is missing."""
    family = normalize_family(family)
    chain = normalize_chain(chain)
    table = FILTER_CHAIN_TABLES[chain]
    db_path = FILTER_FAMILY_DATABASES[family]

    if chain == "INPUT":
        query = f"""
            SELECT id, rule_order, iface_in, '' AS iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   action, protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            WHERE id = ?
        """
    elif chain == "FORWARD":
        query = f"""
            SELECT id, rule_order, iface_in, iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   action, protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            WHERE id = ?
        """
    else:
        query = f"""
            SELECT id, rule_order, '' AS iface_in, iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   action, protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            WHERE id = ?
        """

    with db.connection(db_path) as conn:
        require_filter_chain_policies(conn)
        ensure_pending_delete_column(conn, table)
        row = db.fetch_one_on(conn, query, (rule_id,))

    if row is None:
        raise FilterRuleError("Filter rule not found.", 404)

    return row_to_rule(family, chain, row)


def get_filter_rules() -> dict[str, Any]:
    """Return all persisted filter rules grouped by family and chain."""
    rules: list[dict[str, Any]] = []
    by_chain = {chain: [] for chain in FILTER_CHAIN_TABLES}
    for family in ("IPV4", "IPV6"):
        for chain in ("INPUT", "FORWARD", "OUTPUT"):
            chain_rules = get_rules_for_table(family, chain)
            rules.extend(chain_rules)
            by_chain[chain].extend(chain_rules)
    mark_apply_state(rules)

    enabled = sum(1 for rule in rules if int(rule["enabled"]) == 1)
    protected = sum(1 for rule in rules if int(rule["protected"]) == 1)
    return {
        "summary": {
            "total": len(rules),
            "enabled": enabled,
            "disabled": len(rules) - enabled,
            "protected": protected,
        },
        "chains": by_chain,
        "policies": get_filter_policies(),
        "rules": rules,
    }


def get_filter_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent work requests related to filter rules."""
    query = """
        SELECT
            wr.id,
            wr.request_uid,
            wr.category_name,
            wr.action_name,
            wr.target_rule_id,
            wr.priority,
            wr.status,
            wr.error_message,
            wr.created_at,
            wr.updated_at
        FROM work_requests wr
        WHERE wr.category_name LIKE 'FIREWALL_RULES.%filter_%'
        ORDER BY wr.created_at DESC, wr.id DESC
        LIMIT ?
    """
    with db.connection(WORK_REQUEST_DB_PATH) as conn:
        rows = db.fetch_all_on(conn, query, (limit,))

    summary = {"total": len(rows), "queue": 0, "running": 0, "success": 0, "failed": 0}
    for row in rows:
        status = str(row.get("status", ""))
        if status in summary:
            summary[status] += 1

    return {"summary": summary, "requests": rows}


def sanitize_rule_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an incoming filter rule payload."""
    family = normalize_family(payload.get("family"))
    chain = normalize_chain(payload.get("chain"))
    protocol = normalize_protocol(family, payload.get("protocol_name"))
    action = normalize_action(payload.get("action"))
    is_icmp = protocol in {"icmp", "icmpv6"}
    is_all = protocol == "all"
    has_ports = protocol in {"tcp", "udp"}

    src_port = optional_int(payload.get("src_port", 0)) if has_ports else None
    dst_port = optional_int(payload.get("dst_port", 0)) if has_ports else None
    protocol_type = optional_int(payload.get("protocol_type")) if is_icmp else None
    protocol_code = optional_int(payload.get("protocol_code")) if is_icmp else None

    if has_ports and (src_port is None or dst_port is None):
        raise FilterRuleError("TCP/UDP rules require source and destination ports.", 400)
    if is_icmp and ((protocol_type is None) != (protocol_code is None)):
        raise FilterRuleError("ICMP type and code must be filled together.", 400)

    rule = {
        "family": family,
        "chain": chain,
        "table": FILTER_CHAIN_TABLES[chain],
        "iface_in": str(payload.get("iface_in", "")).strip(),
        "iface_out": str(payload.get("iface_out", "")).strip(),
        "src_addr": str(payload.get("src_addr") or default_address(family)).strip(),
        "src_port": src_port,
        "dst_addr": str(payload.get("dst_addr") or default_address(family)).strip(),
        "dst_port": dst_port,
        "protocol_name": protocol,
        "protocol_type": protocol_type,
        "protocol_code": protocol_code,
        "action": action,
        "enabled": normalize_enabled(payload.get("enabled", 1)),
        "protected": 0,
        "ct_new": normalize_enabled(payload.get("ct_new", 0)),
        "ct_established": normalize_enabled(payload.get("ct_established", 0)),
        "ct_related": normalize_enabled(payload.get("ct_related", 0)),
        "ct_invalid": normalize_enabled(payload.get("ct_invalid", 0)),
    }

    if chain in {"INPUT", "FORWARD"} and not rule["iface_in"]:
        raise FilterRuleError("iface_in is required for INPUT and FORWARD.", 400)
    if chain in {"FORWARD", "OUTPUT"} and not rule["iface_out"]:
        raise FilterRuleError("iface_out is required for FORWARD and OUTPUT.", 400)

    return rule


def insert_rule(conn: db.Connection, rule: dict[str, Any]) -> int:
    """Insert a sanitized filter rule and return its id."""
    table = rule["table"]
    rule_order = next_rule_order(conn, table)

    if rule["chain"] == "INPUT":
        query = f"""
            INSERT INTO {table} (
                iface_in, rule_order, ct_new, ct_established, ct_related, ct_invalid,
                src_addr, src_port, dst_addr, dst_port, protocol_name, protocol_type,
                protocol_code, action, protected, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (
            rule["iface_in"], rule_order, rule["ct_new"], rule["ct_established"], rule["ct_related"], rule["ct_invalid"],
            rule["src_addr"], rule["src_port"], rule["dst_addr"], rule["dst_port"], rule["protocol_name"],
            rule["protocol_type"], rule["protocol_code"], rule["action"], rule["protected"], rule["enabled"],
        )
    elif rule["chain"] == "FORWARD":
        query = f"""
            INSERT INTO {table} (
                iface_in, iface_out, rule_order, ct_new, ct_established, ct_related, ct_invalid,
                src_addr, src_port, dst_addr, dst_port, protocol_name, protocol_type,
                protocol_code, action, protected, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (
            rule["iface_in"], rule["iface_out"], rule_order, rule["ct_new"], rule["ct_established"],
            rule["ct_related"], rule["ct_invalid"], rule["src_addr"], rule["src_port"], rule["dst_addr"],
            rule["dst_port"], rule["protocol_name"], rule["protocol_type"], rule["protocol_code"],
            rule["action"], rule["protected"], rule["enabled"],
        )
    else:
        query = f"""
            INSERT INTO {table} (
                iface_out, rule_order, ct_new, ct_established, ct_related, ct_invalid,
                src_addr, src_port, dst_addr, dst_port, protocol_name, protocol_type,
                protocol_code, action, protected, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (
            rule["iface_out"], rule_order, rule["ct_new"], rule["ct_established"], rule["ct_related"], rule["ct_invalid"],
            rule["src_addr"], rule["src_port"], rule["dst_addr"], rule["dst_port"], rule["protocol_name"],
            rule["protocol_type"], rule["protocol_code"], rule["action"], rule["protected"], rule["enabled"],
        )

    cursor = db.execute_on(conn, query, params)
    return int(cursor.lastrowid)


def enqueue_rule_work_request(category_name: str, action_name: str, rule_id: int | None, payload: dict[str, Any]) -> int:
    """Queue one work request for a firewall rule change."""
    request_uid = str(uuid.uuid4())
    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, payload_json, status
            ) VALUES (?, 'gui', ?, ?, ?, ?, 'queue')
            """,
            (request_uid, category_name, action_name, rule_id, json.dumps(payload, sort_keys=True)),
        )
        request_id = int(cursor.lastrowid)
        db.execute_on(
            conn,
            """
            INSERT INTO work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', ?)
            """,
            (request_id, f"Queued {action_name} for {category_name} rule {rule_id}."),
        )
        return request_id


def enabled_rule_ids_for_chain(family: str, chain: str) -> list[int]:
    """Return enabled rule ids for one family and chain."""
    family = normalize_family(family)
    chain = normalize_chain(chain)
    table = FILTER_CHAIN_TABLES[chain]
    db_path = FILTER_FAMILY_DATABASES[family]

    with db.connection(db_path) as conn:
        require_filter_chain_policies(conn)
        ensure_pending_delete_column(conn, table)
        rows = db.fetch_all_on(conn, f"SELECT id FROM {table} WHERE enabled = 1 AND pending_delete = 0 ORDER BY rule_order, id")

    return [int(row["id"]) for row in rows]


def pending_delete_rule_ids_for_chain(family: str, chain: str) -> list[int]:
    """Return pending delete rule ids for one family and chain."""
    family = normalize_family(family)
    chain = normalize_chain(chain)
    table = FILTER_CHAIN_TABLES[chain]
    db_path = FILTER_FAMILY_DATABASES[family]

    with db.connection(db_path) as conn:
        require_filter_chain_policies(conn)
        ensure_pending_delete_column(conn, table)
        rows = db.fetch_all_on(conn, f"SELECT id FROM {table} WHERE pending_delete = 1 ORDER BY rule_order, id")

    return [int(row["id"]) for row in rows]


def filter_family_needs_apply(family: str, chain: str, apply_times: dict[str, str]) -> bool:
    """Return whether one filter family has pending changes to apply."""
    family = normalize_family(family)
    chain = normalize_chain(chain)
    table = FILTER_CHAIN_TABLES[chain]
    db_path = FILTER_FAMILY_DATABASES[family]
    category_name = f"FIREWALL_RULES.{family}.{table}"
    applied_at = apply_times.get(category_name)

    with db.connection(db_path) as conn:
        require_filter_chain_policies(conn)
        ensure_pending_delete_column(conn, table)
        policy_row = db.fetch_one_on(
            conn,
            "SELECT policy, updated_at FROM filter_chain_policies WHERE chain_name = ?",
            (chain,),
        )
        if policy_row is not None:
            default_policy = FILTER_DEFAULT_POLICIES[chain]
            policy_changed_without_apply = applied_at is None and str(policy_row["policy"]) != default_policy
            policy_changed_after_apply = applied_at is not None and str(policy_row["updated_at"]) > applied_at
            if policy_changed_without_apply or policy_changed_after_apply:
                return True

        pending_delete = db.fetch_one_on(conn, f"SELECT COUNT(*) AS total FROM {table} WHERE pending_delete = 1")
        if int(pending_delete["total"]) > 0:
            return True

        if applied_at is None:
            pending_enabled = db.fetch_one_on(
                conn,
                f"SELECT COUNT(*) AS total FROM {table} WHERE protected = 0 AND enabled = 1 AND pending_delete = 0",
            )
            return int(pending_enabled["total"]) > 0

        changed_rows = db.fetch_one_on(
            conn,
            f"SELECT COUNT(*) AS total FROM {table} WHERE protected = 0 AND updated_at > ?",
            (applied_at,),
        )
        return int(changed_rows["total"]) > 0


def create_filter_rule(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a filter rule without applying it to the operating system."""
    rule = sanitize_rule_payload(payload)
    db_path = FILTER_FAMILY_DATABASES[rule["family"]]

    with db.transaction(db_path) as conn:
        require_filter_chain_policies(conn)
        ensure_pending_delete_column(conn, rule["table"])
        rule_id = insert_rule(conn, rule)

    return {"rule_id": rule_id, "status": "saved"}


def update_filter_rule(family_value: str, chain_value: str, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update an editable filter rule without applying it to the operating system."""
    family = normalize_family(family_value)
    chain = normalize_chain(chain_value)
    table = FILTER_CHAIN_TABLES[chain]
    db_path = FILTER_FAMILY_DATABASES[family]
    payload = dict(payload)
    payload["family"] = family
    payload["chain"] = chain
    rule = sanitize_rule_payload(payload)

    with db.transaction(db_path) as conn:
        require_filter_chain_policies(conn)
        ensure_pending_delete_column(conn, table)
        current = db.fetch_one_on(conn, f"SELECT protected, enabled, pending_delete FROM {table} WHERE id = ?", (rule_id,))
        if current is None:
            raise FilterRuleError("Filter rule not found.", 404)
        if int(current["pending_delete"]) == 1:
            raise FilterRuleError("Filter rules pending deletion cannot be edited.", 403)
        if int(current["enabled"]) == 0:
            raise FilterRuleError("Disabled filter rules cannot be edited.", 403)
        if int(current["protected"]) == 1:
            raise FilterRuleError("Protected filter rules cannot be edited.", 403)

        if chain == "INPUT":
            query = f"""
                UPDATE {table}
                SET iface_in = ?, ct_new = ?, ct_established = ?, ct_related = ?, ct_invalid = ?,
                    src_addr = ?, src_port = ?, dst_addr = ?, dst_port = ?,
                    protocol_name = ?, protocol_type = ?, protocol_code = ?,
                    action = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (
                rule["iface_in"], rule["ct_new"], rule["ct_established"], rule["ct_related"], rule["ct_invalid"],
                rule["src_addr"], rule["src_port"], rule["dst_addr"], rule["dst_port"], rule["protocol_name"],
                rule["protocol_type"], rule["protocol_code"], rule["action"], rule["enabled"], rule_id,
            )
        elif chain == "FORWARD":
            query = f"""
                UPDATE {table}
                SET iface_in = ?, iface_out = ?,
                    ct_new = ?, ct_established = ?, ct_related = ?, ct_invalid = ?,
                    src_addr = ?, src_port = ?, dst_addr = ?, dst_port = ?,
                    protocol_name = ?, protocol_type = ?, protocol_code = ?,
                    action = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (
                rule["iface_in"], rule["iface_out"], rule["ct_new"], rule["ct_established"], rule["ct_related"],
                rule["ct_invalid"], rule["src_addr"], rule["src_port"], rule["dst_addr"], rule["dst_port"],
                rule["protocol_name"], rule["protocol_type"], rule["protocol_code"], rule["action"], rule["enabled"], rule_id,
            )
        else:
            query = f"""
                UPDATE {table}
                SET iface_out = ?, ct_new = ?, ct_established = ?, ct_related = ?, ct_invalid = ?,
                    src_addr = ?, src_port = ?, dst_addr = ?, dst_port = ?,
                    protocol_name = ?, protocol_type = ?, protocol_code = ?,
                    action = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (
                rule["iface_out"], rule["ct_new"], rule["ct_established"], rule["ct_related"], rule["ct_invalid"],
                rule["src_addr"], rule["src_port"], rule["dst_addr"], rule["dst_port"], rule["protocol_name"],
                rule["protocol_type"], rule["protocol_code"], rule["action"], rule["enabled"], rule_id,
            )

        db.execute_on(conn, query, params)

    return {"rule_id": rule_id, "status": "saved"}


def apply_filter_rule(family_value: str, chain_value: str, rule_id: int) -> dict[str, Any]:
    """Reject per-rule application so only the chain Apply button can run."""
    normalize_family(family_value)
    normalize_chain(chain_value)
    raise FilterRuleError("Rules can only be applied with the chain Apply button.", 403)


def apply_filter_chain(chain_value: str, family_value: Any | None = None) -> dict[str, Any]:
    """Queue only filter families with pending changes for one chain."""
    chain = normalize_chain(chain_value)
    table = FILTER_CHAIN_TABLES[chain]
    apply_times = last_successful_apply_times()
    families = (normalize_family(family_value),) if family_value else ("IPV4", "IPV6")
    work_requests = []

    for family in families:
        if not filter_family_needs_apply(family, chain, apply_times):
            continue

        rule_ids = enabled_rule_ids_for_chain(family, chain)
        delete_rule_ids = pending_delete_rule_ids_for_chain(family, chain)
        policy = get_filter_policies().get(chain, {}).get(family, {}).get("policy", FILTER_DEFAULT_POLICIES[chain])
        category_name = f"FIREWALL_RULES.{family}.{table}"
        payload = {
            "family": family,
            "chain": chain,
            "table": table,
            "policy": policy,
            "rule_ids": rule_ids,
            "delete_rule_ids": delete_rule_ids,
        }
        work_request_id = enqueue_rule_work_request(category_name, "apply", None, payload)
        work_requests.append(
            {
                "family": family,
                "chain": chain,
                "category_name": category_name,
                "work_request_id": work_request_id,
                "rule_count": len(rule_ids),
            }
        )

    return {"chain": chain, "family": family_value or "ALL", "work_requests": work_requests, "work_request_count": len(work_requests)}


def set_filter_chain_policy(chain_value: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a filter chain policy without applying it."""
    chain = normalize_chain(chain_value)
    family = normalize_family(payload.get("family"))
    policy = normalize_policy(payload.get("policy"))

    with db.transaction(FILTER_FAMILY_DATABASES[family]) as conn:
        require_filter_chain_policies(conn)
        db.execute_on(
            conn,
            """
            UPDATE filter_chain_policies
            SET policy = ?, updated_at = CURRENT_TIMESTAMP
            WHERE chain_name = ?
            """,
            (policy, chain),
        )

    return {"chain": chain, "family": family, "policy": policy, "status": "saved"}


def set_filter_rule_enabled(family_value: str, chain_value: str, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update the enabled flag for a filter rule without applying it."""
    family = normalize_family(family_value)
    chain = normalize_chain(chain_value)
    table = FILTER_CHAIN_TABLES[chain]
    enabled = normalize_enabled(payload.get("enabled", 0))
    db_path = FILTER_FAMILY_DATABASES[family]

    with db.transaction(db_path) as conn:
        require_filter_chain_policies(conn)
        ensure_pending_delete_column(conn, table)
        current = db.fetch_one_on(conn, f"SELECT enabled, protected, pending_delete FROM {table} WHERE id = ?", (rule_id,))
        if current is None:
            raise FilterRuleError("Filter rule not found.", 404)
        if int(current["pending_delete"]) == 1:
            raise FilterRuleError("Filter rules pending deletion cannot be changed.", 403)
        if int(current["protected"]) == 1 and enabled == 0:
            raise FilterRuleError("Protected filter rules cannot be disabled.", 403)

        cursor = db.execute_on(
            conn,
            f"UPDATE {table} SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (enabled, rule_id),
        )

    return {"rule_id": rule_id, "enabled": enabled, "status": "saved"}


def delete_filter_rule(family_value: str, chain_value: str, rule_id: int) -> dict[str, Any]:
    """Mark an editable filter rule for deletion on the next Apply."""
    family = normalize_family(family_value)
    chain = normalize_chain(chain_value)
    table = FILTER_CHAIN_TABLES[chain]
    db_path = FILTER_FAMILY_DATABASES[family]
    rule = get_filter_rule(family, chain, rule_id)

    if int(rule["enabled"]) == 0:
        raise FilterRuleError("Disabled filter rules cannot be deleted.", 403)
    if int(rule["protected"]) == 1:
        raise FilterRuleError("Protected filter rules cannot be deleted.", 403)

    if int(rule.get("pending_delete") or 0) == 1:
        return {"rule_id": rule_id, "status": "saved"}

    with db.transaction(db_path) as conn:
        ensure_pending_delete_column(conn, table)
        db.execute_on(conn, f"UPDATE {table} SET pending_delete = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (rule_id,))

    return {"rule_id": rule_id, "status": "saved"}
