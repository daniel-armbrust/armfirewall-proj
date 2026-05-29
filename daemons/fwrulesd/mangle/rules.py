from __future__ import annotations

import json
import uuid
from functools import partial
from typing import Any

from core import db
from core.constants import WORK_REQUEST_DB_PATH
from daemons.fwrulesd import commons
from daemons.fwrulesd.constants import (
    MANGLE_ACTIONS,
    MANGLE_CHAIN_TABLES,
    MANGLE_FAMILY_DATABASES,
)


class MangleRuleError(commons.FirewallRuleError):
    """Mangle rule failure with an HTTP-friendly status code for callers."""


normalize_family = partial(
    commons.normalize_family,
    family_databases=MANGLE_FAMILY_DATABASES,
    error_cls=MangleRuleError,
)
normalize_chain = partial(
    commons.normalize_chain,
    chain_tables=MANGLE_CHAIN_TABLES,
    default="PREROUTING",
    error_message="Unsupported mangle chain.",
    error_cls=MangleRuleError,
)
normalize_protocol = partial(commons.normalize_protocol, error_cls=MangleRuleError)
normalize_enabled = commons.normalize_enabled
default_address = commons.default_address
optional_int = partial(commons.optional_int, error_cls=MangleRuleError)
next_rule_order = commons.next_rule_order
ensure_pending_delete_column = commons.ensure_pending_delete_column
row_to_rule = partial(commons.row_to_rule, chain_tables=MANGLE_CHAIN_TABLES)
last_successful_apply_times = partial(commons.last_successful_apply_times, "MANGLE_RULES.%mangle_%")
mark_apply_state = partial(
    commons.mark_apply_state,
    category_prefix="MANGLE_RULES",
    apply_times_callback=last_successful_apply_times,
)


def normalize_mangle_action(value: Any) -> str:
    """Normalize and validate a mangle target action."""
    action = str(value or "ACCEPT").strip().upper()
    if action not in MANGLE_ACTIONS:
        raise MangleRuleError("Unsupported mangle action.", 400)
    return action


def get_rules_for_table(family: str, chain: str) -> list[dict[str, Any]]:
    """Read rules from one mangle chain table."""
    table = MANGLE_CHAIN_TABLES[chain]
    db_path = MANGLE_FAMILY_DATABASES[family]

    if chain in {"PREROUTING", "INPUT"}:
        query = f"""
            SELECT id, rule_order, iface_in, '' AS iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                   protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            ORDER BY rule_order, id
        """
    elif chain == "FORWARD":
        query = f"""
            SELECT id, rule_order, iface_in, iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                   protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            ORDER BY rule_order, id
        """
    else:
        query = f"""
            SELECT id, rule_order, '' AS iface_in, iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                   protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            ORDER BY rule_order, id
        """

    with db.connection(db_path) as conn:
        ensure_pending_delete_column(conn, table)
        return [row_to_rule(family, chain, row) for row in db.execute_on(conn, query).fetchall()]


def get_mangle_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Return one persisted mangle rule or fail when it is missing."""
    family = normalize_family(family)
    chain = normalize_chain(chain)
    table = MANGLE_CHAIN_TABLES[chain]
    db_path = MANGLE_FAMILY_DATABASES[family]

    if chain in {"PREROUTING", "INPUT"}:
        query = f"""
            SELECT id, rule_order, iface_in, '' AS iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                   protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            WHERE id = ?
        """
    elif chain == "FORWARD":
        query = f"""
            SELECT id, rule_order, iface_in, iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                   protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            WHERE id = ?
        """
    else:
        query = f"""
            SELECT id, rule_order, '' AS iface_in, iface_out,
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                   protected, enabled, pending_delete, created_at, updated_at
            FROM {table}
            WHERE id = ?
        """

    with db.connection(db_path) as conn:
        ensure_pending_delete_column(conn, table)
        row = db.fetch_one_on(conn, query, (rule_id,))

    if row is None:
        raise MangleRuleError("Mangle rule not found.", 404)

    return row_to_rule(family, chain, row)


def get_mangle_rules() -> dict[str, Any]:
    """Return all persisted IPv4 and IPv6 mangle rules grouped by chain."""
    rules: list[dict[str, Any]] = []
    by_chain = {chain: [] for chain in MANGLE_CHAIN_TABLES}
    for family in ("IPV4", "IPV6"):
        for chain in ("PREROUTING", "INPUT", "FORWARD", "OUTPUT", "POSTROUTING"):
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
        "rules": rules,
    }


def get_mangle_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent work requests for mangle firewall rules."""
    query = """
        SELECT
            wr.id, wr.request_uid, wr.status, wr.source,
            wr.category_name, wr.action_name, wr.target_rule_id,
            wr.error_message, wr.created_at, wr.updated_at
        FROM work_requests wr
        WHERE wr.category_name LIKE 'MANGLE_RULES.%mangle_%'
        ORDER BY wr.id DESC
        LIMIT ?
    """

    with db.connection(WORK_REQUEST_DB_PATH) as conn:
        rows = db.fetch_all_on(conn, query, (limit,))
    return {"requests": [db.row_to_dict(row) for row in rows]}


def enqueue_mangle_work_request(category_name: str, action_name: str, rule_id: int | None, payload: dict[str, Any]) -> int:
    """Queue a mangle rule work request for the daemon."""
    request_uid = str(uuid.uuid4())

    with db.connection(WORK_REQUEST_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, payload_json, status
            )
            VALUES (?, 'gui', ?, ?, ?, ?, 'queue')
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
            (request_id, f"Queued {action_name} for {category_name}."),
        )
        conn.commit()

    return request_id


def sanitize_mangle_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an incoming mangle rule payload."""
    family = normalize_family(payload.get("family"))
    chain = normalize_chain(payload.get("chain"))
    protocol = normalize_protocol(family, payload.get("protocol_name"))
    is_icmp = protocol in {"icmp", "icmpv6"}
    is_all = protocol == "all"

    rule = {
        "family": family,
        "chain": chain,
        "table": MANGLE_CHAIN_TABLES[chain],
        "iface_in": str(payload.get("iface_in", "")).strip(),
        "iface_out": str(payload.get("iface_out", "")).strip(),
        "ct_new": normalize_enabled(payload.get("ct_new", 0)),
        "ct_established": normalize_enabled(payload.get("ct_established", 0)),
        "ct_related": normalize_enabled(payload.get("ct_related", 0)),
        "ct_invalid": normalize_enabled(payload.get("ct_invalid", 0)),
        "src_addr": str(payload.get("src_addr") or default_address(family)).strip(),
        "src_port": None if is_icmp or is_all else optional_int(payload.get("src_port", 0)),
        "dst_addr": str(payload.get("dst_addr") or default_address(family)).strip(),
        "dst_port": None if is_icmp or is_all else optional_int(payload.get("dst_port", 0)),
        "protocol_name": protocol,
        "protocol_type": optional_int(payload.get("protocol_type")) if is_icmp else None,
        "protocol_code": optional_int(payload.get("protocol_code")) if is_icmp else None,
        "mangle_action": normalize_mangle_action(payload.get("mangle_action")),
        "mark_value": str(payload.get("mark_value", "")).strip() or None,
        "dscp_value": str(payload.get("dscp_value", "")).strip() or None,
        "tos_value": str(payload.get("tos_value", "")).strip() or None,
        "ttl_value": str(payload.get("ttl_value", "")).strip() or None,
        "enabled": normalize_enabled(payload.get("enabled", 1)),
        "protected": 0,
    }

    if chain in {"PREROUTING", "INPUT", "FORWARD"} and not rule["iface_in"]:
        raise MangleRuleError("iface_in is required for PREROUTING, INPUT, and FORWARD.", 400)
    if chain in {"FORWARD", "OUTPUT", "POSTROUTING"} and not rule["iface_out"]:
        raise MangleRuleError("iface_out is required for FORWARD, OUTPUT, and POSTROUTING.", 400)
    if is_icmp and ((rule["protocol_type"] is None) != (rule["protocol_code"] is None)):
        raise MangleRuleError("ICMP type and code must be filled together.", 400)

    return rule


def insert_mangle_rule(conn: db.Connection, rule: dict[str, Any]) -> int:
    """Insert a sanitized mangle rule and return its id."""
    table = rule["table"]
    rule_order = next_rule_order(conn, table)
    common_values = (
        rule_order, rule["ct_new"], rule["ct_established"], rule["ct_related"], rule["ct_invalid"],
        rule["src_addr"], rule["src_port"], rule["dst_addr"], rule["dst_port"], rule["protocol_name"],
        rule["protocol_type"], rule["protocol_code"], rule["mangle_action"], rule["mark_value"],
        rule["dscp_value"], rule["tos_value"], rule["ttl_value"], rule["protected"], rule["enabled"],
    )

    if rule["chain"] in {"PREROUTING", "INPUT"}:
        query = f"""
            INSERT INTO {table} (
                iface_in, rule_order, ct_new, ct_established, ct_related, ct_invalid,
                src_addr, src_port, dst_addr, dst_port, protocol_name, protocol_type,
                protocol_code, mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                protected, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (rule["iface_in"], *common_values)
    elif rule["chain"] == "FORWARD":
        query = f"""
            INSERT INTO {table} (
                iface_in, iface_out, rule_order, ct_new, ct_established, ct_related, ct_invalid,
                src_addr, src_port, dst_addr, dst_port, protocol_name, protocol_type,
                protocol_code, mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                protected, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (rule["iface_in"], rule["iface_out"], *common_values)
    else:
        query = f"""
            INSERT INTO {table} (
                iface_out, rule_order, ct_new, ct_established, ct_related, ct_invalid,
                src_addr, src_port, dst_addr, dst_port, protocol_name, protocol_type,
                protocol_code, mangle_action, mark_value, dscp_value, tos_value, ttl_value,
                protected, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (rule["iface_out"], *common_values)

    cursor = db.execute_on(conn, query, params)
    return int(cursor.lastrowid)


def create_mangle_rule(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a mangle rule without applying it to the operating system."""
    rule = sanitize_mangle_payload(payload)
    db_path = MANGLE_FAMILY_DATABASES[rule["family"]]

    with db.transaction(db_path) as conn:
        ensure_pending_delete_column(conn, rule["table"])
        rule_id = insert_mangle_rule(conn, rule)

    return {"rule_id": rule_id, "status": "saved"}


def mangle_family_needs_apply(family: str, chain: str, apply_times: dict[str, str]) -> bool:
    """Return whether one mangle family has pending changes to apply."""
    family = normalize_family(family)
    chain = normalize_chain(chain)
    table = MANGLE_CHAIN_TABLES[chain]
    db_path = MANGLE_FAMILY_DATABASES[family]
    category_name = f"MANGLE_RULES.{family}.{table}"
    applied_at = apply_times.get(category_name)

    with db.connection(db_path) as conn:
        ensure_pending_delete_column(conn, table)
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


def apply_mangle_chain(chain: str, family_value: Any = None) -> dict[str, Any]:
    """Queue only mangle families with pending changes for one chain."""
    chain = chain.strip().upper()
    if chain not in MANGLE_CHAIN_TABLES:
        raise MangleRuleError("Unsupported mangle chain.", 400)

    table = MANGLE_CHAIN_TABLES[chain]
    apply_times = last_successful_apply_times()
    family_databases = {normalize_family(family_value): MANGLE_FAMILY_DATABASES[normalize_family(family_value)]} if family_value else MANGLE_FAMILY_DATABASES
    work_requests = []
    for family, db_path in family_databases.items():
        if not mangle_family_needs_apply(family, chain, apply_times):
            continue

        with db.connection(db_path) as conn:
            ensure_pending_delete_column(conn, table)
            rows = db.fetch_all_on(conn, f"SELECT id FROM {table} WHERE enabled = 1 AND pending_delete = 0 ORDER BY rule_order, id")
            delete_rows = db.fetch_all_on(conn, f"SELECT id FROM {table} WHERE pending_delete = 1 ORDER BY rule_order, id")

        rule_ids = [int(row["id"]) for row in rows]
        delete_rule_ids = [int(row["id"]) for row in delete_rows]
        category_name = f"MANGLE_RULES.{family}.{table}"
        payload = {"family": family, "chain": chain, "table": table, "rule_ids": rule_ids, "delete_rule_ids": delete_rule_ids}
        work_request_id = enqueue_mangle_work_request(category_name, "apply", None, payload)
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


def set_mangle_rule_enabled(family_value: str, chain_value: str, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update the enabled flag for a mangle rule without applying it."""
    family = normalize_family(family_value)
    chain = normalize_chain(chain_value)
    table = MANGLE_CHAIN_TABLES[chain]
    enabled = normalize_enabled(payload.get("enabled", 0))
    db_path = MANGLE_FAMILY_DATABASES[family]

    with db.transaction(db_path) as conn:
        ensure_pending_delete_column(conn, table)
        current = db.fetch_one_on(conn, f"SELECT enabled, protected, pending_delete FROM {table} WHERE id = ?", (rule_id,))
        if current is None:
            raise MangleRuleError("Mangle rule not found.", 404)
        if int(current["pending_delete"]) == 1:
            raise MangleRuleError("Mangle rules pending deletion cannot be changed.", 403)
        if int(current["protected"]) == 1 and enabled == 0:
            raise MangleRuleError("Protected mangle rules cannot be disabled.", 403)

        db.execute_on(
            conn,
            f"UPDATE {table} SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (enabled, rule_id),
        )

    return {"rule_id": rule_id, "enabled": enabled, "status": "saved"}


def delete_mangle_rule(family_value: str, chain_value: str, rule_id: int) -> dict[str, Any]:
    """Mark an editable mangle rule for deletion on the next Apply."""
    family = normalize_family(family_value)
    chain = normalize_chain(chain_value)
    table = MANGLE_CHAIN_TABLES[chain]
    db_path = MANGLE_FAMILY_DATABASES[family]
    rule = get_mangle_rule(family, chain, rule_id)

    if int(rule["enabled"]) == 0:
        raise MangleRuleError("Disabled mangle rules cannot be deleted.", 403)
    if int(rule["protected"]) == 1:
        raise MangleRuleError("Protected mangle rules cannot be deleted.", 403)

    if int(rule.get("pending_delete") or 0) == 1:
        return {"rule_id": rule_id, "status": "saved"}

    with db.transaction(db_path) as conn:
        ensure_pending_delete_column(conn, table)
        db.execute_on(conn, f"UPDATE {table} SET pending_delete = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (rule_id,))

    return {"rule_id": rule_id, "status": "saved"}
