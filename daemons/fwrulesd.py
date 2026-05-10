#!/usr/bin/env python3
"""One-shot firewall rule executor used by the work request daemon."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import db
from core import log as logger

DB_DIR = ROOT_DIR / "db"
LOG_SOURCE = "fwrulesd.py"


RULE_DATABASES = {
    ("FIREWALL_RULES", "IPV4"): DB_DIR / "ipv4-firewall-rules.db",
    ("FIREWALL_RULES", "IPV6"): DB_DIR / "ipv6-firewall-rules.db",
    ("NAT_RULES", "IPV4"): DB_DIR / "ipv4-nat-rules.db",
    ("NAT_RULES", "IPV6"): DB_DIR / "ipv6-nat-rules.db",
    ("MANGLE_RULES", "IPV4"): DB_DIR / "ipv4-mangle-rules.db",
    ("MANGLE_RULES", "IPV6"): DB_DIR / "ipv6-mangle-rules.db",
}

TABLE_METADATA = {
    "filter_input_rules": ("filter", "INPUT"),
    "filter_forward_rules": ("filter", "FORWARD"),
    "filter_output_rules": ("filter", "OUTPUT"),
    "nat_prerouting_rules": ("nat", "PREROUTING"),
    "nat_input_rules": ("nat", "INPUT"),
    "nat_output_rules": ("nat", "OUTPUT"),
    "nat_postrouting_rules": ("nat", "POSTROUTING"),
    "mangle_prerouting_rules": ("mangle", "PREROUTING"),
    "mangle_input_rules": ("mangle", "INPUT"),
    "mangle_forward_rules": ("mangle", "FORWARD"),
    "mangle_output_rules": ("mangle", "OUTPUT"),
    "mangle_postrouting_rules": ("mangle", "POSTROUTING"),
}

SELECT_COLUMNS = {
    "filter_input_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        action, protected, enabled, created_at, updated_at
    """,
    "filter_forward_rules": """
        id, rule_order, iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        action, protected, enabled, created_at, updated_at
    """,
    "filter_output_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        action, protected, enabled, created_at, updated_at
    """,
    "nat_prerouting_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        nat_action, to_addr, to_port,
        protected, enabled, created_at, updated_at
    """,
    "nat_input_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        nat_action, to_addr, to_port,
        protected, enabled, created_at, updated_at
    """,
    "nat_output_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        nat_action, to_addr, to_port,
        protected, enabled, created_at, updated_at
    """,
    "nat_postrouting_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        nat_action, to_addr, to_port,
        protected, enabled, created_at, updated_at
    """,
    "mangle_prerouting_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
    "mangle_input_rules": """
        id, rule_order, iface_in, '' AS iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
    "mangle_forward_rules": """
        id, rule_order, iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
    "mangle_output_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
    "mangle_postrouting_rules": """
        id, rule_order, '' AS iface_in, iface_out,
        ct_new, ct_established, ct_related, ct_invalid,
        src_addr, src_port, dst_addr, dst_port,
        protocol_name, protocol_type, protocol_code,
        mangle_action, mark_value, dscp_value, tos_value, ttl_value,
        protected, enabled, created_at, updated_at
    """,
}

WILDCARD_ADDRESSES = {"0.0.0.0/0", "::/0", "", None}
FILTER_POLICY_CHAINS = ("INPUT", "FORWARD")
FILTER_RULE_TABLES = ("filter_input_rules", "filter_forward_rules", "filter_output_rules")
PROTECTED_RULE_TABLES = {
    "FIREWALL_RULES": FILTER_RULE_TABLES,
    "NAT_RULES": ("nat_prerouting_rules", "nat_input_rules", "nat_output_rules", "nat_postrouting_rules"),
    "MANGLE_RULES": (
        "mangle_prerouting_rules",
        "mangle_input_rules",
        "mangle_forward_rules",
        "mangle_output_rules",
        "mangle_postrouting_rules",
    ),
}


def database_for_request(category: str, family: str) -> Path:
    """Return the SQLite database used by one rule work request."""
    db_path = RULE_DATABASES.get((category, family))
    if db_path is None:
        raise RuntimeError(f"Unsupported rule database mapping: category={category}, family={family}")
    return db_path


def verify_rule_database(category: str, family: str) -> None:
    """Verify that the rule database for one work request can be opened."""
    with db.connection(database_for_request(category, family)) as conn:
        db.fetch_one_on(conn, "SELECT 1")


def ensure_pending_delete_column(conn: db.Connection, table: str) -> None:
    """Add the pending delete marker to older rule tables when needed."""
    columns = {str(row["name"]) for row in db.execute_on(conn, f"PRAGMA table_info({table})").fetchall()}
    if "pending_delete" not in columns:
        db.execute_on(conn, f"ALTER TABLE {table} ADD COLUMN pending_delete INTEGER NOT NULL DEFAULT 0")


def payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Decode the work request JSON payload."""
    try:
        payload = json.loads(args.payload_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Payload JSON must decode to an object.")
    return payload


def table_from_request(args: argparse.Namespace, payload: dict[str, Any]) -> str:
    """Return the target SQLite table name for a request."""
    table = str(payload.get("table") or args.target_name or "").strip()
    if table not in TABLE_METADATA:
        raise RuntimeError(f"Unsupported rule table: {table}")
    return table


def command_name(family: str) -> str:
    """Return the iptables command for one address family."""
    return "ip6tables" if family == "IPV6" else "iptables"


def add_if_value(command: list[str], flag: str, value: Any) -> None:
    """Append a command argument pair when the value is meaningful."""
    if value is None:
        return
    text = str(value).strip()
    if text:
        command.extend([flag, text])


def add_address_match(command: list[str], flag: str, value: Any) -> None:
    """Append a source or destination address match when not wildcard."""
    if value in WILDCARD_ADDRESSES:
        return
    add_if_value(command, flag, value)


def is_real_port(value: Any) -> bool:
    """Return whether a port value should be added to iptables."""
    if value is None:
        return False
    text = str(value).strip()
    return bool(text and text != "0")


def add_protocol_match(command: list[str], family: str, rule: dict[str, Any]) -> None:
    """Append protocol, port, and ICMP matches for one rule."""
    protocol = str(rule.get("protocol_name") or "all").lower()
    if protocol == "all":
        return

    iptables_protocol = "ipv6-icmp" if family == "IPV6" and protocol in {"icmp", "icmpv6"} else protocol
    command.extend(["-p", iptables_protocol])

    if protocol in {"tcp", "udp"}:
        if is_real_port(rule.get("src_port")):
            command.extend(["--sport", str(rule["src_port"])])
        if is_real_port(rule.get("dst_port")):
            command.extend(["--dport", str(rule["dst_port"])])
        return

    if protocol in {"icmp", "icmpv6"} and rule.get("protocol_type") is not None:
        icmp_flag = "--icmpv6-type" if family == "IPV6" else "--icmp-type"
        icmp_value = str(rule["protocol_type"])
        if rule.get("protocol_code") is not None:
            icmp_value = f"{icmp_value}/{rule['protocol_code']}"
        command.extend([icmp_flag, icmp_value])


def add_conntrack_match(command: list[str], rule: dict[str, Any]) -> None:
    """Append conntrack state matches for filter and mangle rules."""
    states = []
    for column, state in (
        ("ct_new", "NEW"),
        ("ct_established", "ESTABLISHED"),
        ("ct_related", "RELATED"),
        ("ct_invalid", "INVALID"),
    ):
        if int(rule.get(column) or 0) == 1:
            states.append(state)
    if states:
        command.extend(["-m", "conntrack", "--ctstate", ",".join(states)])


def add_interface_matches(command: list[str], chain: str, rule: dict[str, Any]) -> None:
    """Append input and output interface matches for the selected chain."""
    if chain in {"INPUT", "FORWARD", "PREROUTING"}:
        add_if_value(command, "-i", rule.get("iface_in"))
    if chain in {"OUTPUT", "FORWARD", "POSTROUTING"}:
        add_if_value(command, "-o", rule.get("iface_out"))


def add_nat_target_options(command: list[str], action: str, rule: dict[str, Any]) -> None:
    """Append target-specific NAT options."""
    to_addr = rule.get("to_addr")
    to_port = rule.get("to_port")

    if action == "DNAT" and to_addr:
        value = str(to_addr)
        if is_real_port(to_port):
            value = f"{value}:{to_port}"
        command.extend(["--to-destination", value])
    elif action == "SNAT" and to_addr:
        value = str(to_addr)
        if is_real_port(to_port):
            value = f"{value}:{to_port}"
        command.extend(["--to-source", value])
    elif action == "REDIRECT" and is_real_port(to_port):
        command.extend(["--to-ports", str(to_port)])


def add_mangle_target_options(command: list[str], action: str, rule: dict[str, Any]) -> None:
    """Append target-specific mangle options."""
    if action in {"MARK", "CONNMARK"} and rule.get("mark_value"):
        option = "--set-mark" if action == "MARK" else "--set-xmark"
        command.extend([option, str(rule["mark_value"])])
    elif action == "DSCP" and rule.get("dscp_value"):
        command.extend(["--set-dscp", str(rule["dscp_value"])])
    elif action == "TOS" and rule.get("tos_value"):
        command.extend(["--set-tos", str(rule["tos_value"])])
    elif action == "TTL" and rule.get("ttl_value"):
        command.extend(["--ttl-set", str(rule["ttl_value"])])


def rule_spec(args: argparse.Namespace, table: str, chain: str, rule: dict[str, Any]) -> list[str]:
    """Build the common iptables rule specification without operation."""
    family = args.family
    command = [command_name(family), "-t", table, chain]

    add_interface_matches(command, chain, rule)
    add_address_match(command, "-s", rule.get("src_addr"))
    add_address_match(command, "-d", rule.get("dst_addr"))
    add_protocol_match(command, family, rule)
    if table in {"filter", "mangle"}:
        add_conntrack_match(command, rule)

    if table == "filter":
        action = str(rule.get("action") or "ACCEPT").upper()
    elif table == "nat":
        action = str(rule.get("nat_action") or "ACCEPT").upper()
    else:
        action = str(rule.get("mangle_action") or "ACCEPT").upper()

    command.extend(["-j", action])

    if table == "nat":
        add_nat_target_options(command, action, rule)
    elif table == "mangle":
        add_mangle_target_options(command, action, rule)

    return command


def run_command(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run one iptables command and optionally raise with stderr on failure."""
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if check and completed.returncode != 0:
        rendered = " ".join(command)
        message = (completed.stderr or completed.stdout or "command failed").strip()
        raise RuntimeError(f"{rendered}: {message}")
    return completed


def enforce_filter_drop_policies() -> int:
    """Ensure protected filter chains keep their DROP policy."""
    changed = 0
    for family in ("IPV4", "IPV6"):
        command = command_name(family)
        for chain in FILTER_POLICY_CHAINS:
            row = run_command([command, "-t", "filter", "-S", chain], check=False)
            expected = f"-P {chain} DROP"
            if row.returncode == 0 and expected in row.stdout.splitlines():
                continue
            run_command([command, "-t", "filter", "-P", chain, "DROP"])
            changed += 1
    return changed


def apply_rule(args: argparse.Namespace, rule: dict[str, Any]) -> bool:
    """Apply one rule when it is enabled and not already present."""
    if int(rule.get("enabled") or 0) == 0:
        return False

    table_name = table_from_request(args, rule)
    iptables_table, chain = TABLE_METADATA[table_name]
    spec = rule_spec(args, iptables_table, chain, rule)
    check_command = [*spec[:3], "-C", *spec[3:]]
    add_command = [*spec[:3], "-A", *spec[3:]]

    if run_command(check_command, check=False).returncode == 0:
        return False

    run_command(add_command)
    return True


def remove_rule(args: argparse.Namespace, rule: dict[str, Any]) -> int:
    """Remove all operating system copies matching one rule."""
    table_name = table_from_request(args, rule)
    iptables_table, chain = TABLE_METADATA[table_name]
    spec = rule_spec(args, iptables_table, chain, rule)
    delete_command = [*spec[:3], "-D", *spec[3:]]
    removed = 0

    while True:
        completed = run_command(delete_command, check=False)
        if completed.returncode != 0:
            break
        removed += 1

    return removed


def fetch_protected_rules(category: str, family: str) -> list[dict[str, Any]]:
    """Return all enabled protected rules for one category and family."""
    db_path = database_for_request(category, family)
    rules: list[dict[str, Any]] = []

    with db.transaction(db_path) as conn:
        for table in PROTECTED_RULE_TABLES[category]:
            ensure_pending_delete_column(conn, table)
            columns = SELECT_COLUMNS[table]
            rows = db.fetch_all_on(
                conn,
                f"""
                SELECT {columns}
                FROM {table}
                WHERE protected = 1
                  AND enabled = 1
                  AND COALESCE(pending_delete, 0) = 0
                ORDER BY rule_order, id
                """,
            )
            for row in rows:
                rule = dict(row)
                rule["family"] = family
                rule["table"] = table
                rules.append(rule)

    return rules


def reconcile_protected_rules() -> int:
    """Reapply any missing protected rule from SQLite."""
    applied = 0
    for category in ("FIREWALL_RULES", "NAT_RULES", "MANGLE_RULES"):
        for family in ("IPV4", "IPV6"):
            rule_args = argparse.Namespace(family=family, target_name=None)
            for rule in fetch_protected_rules(category, family):
                applied += 1 if apply_rule(rule_args, rule) else 0
    return applied


def flush_chain(args: argparse.Namespace, table_name: str) -> None:
    """Flush one operating system chain before a full chain apply."""
    iptables_table, chain = TABLE_METADATA[table_name]
    run_command([command_name(args.family), "-t", iptables_table, "-F", chain])


def purge_pending_delete_rules(args: argparse.Namespace, table: str, payload: dict[str, Any]) -> int:
    """Remove rules from SQLite after a successful full chain apply."""
    rule_ids = payload.get("delete_rule_ids")
    if not isinstance(rule_ids, list) or not rule_ids:
        return 0

    placeholders = ",".join("?" for _ in rule_ids)
    with db.transaction(database_for_request(args.category, args.family)) as conn:
        cursor = db.execute_on(
            conn,
            f"DELETE FROM {table} WHERE pending_delete = 1 AND id IN ({placeholders})",
            tuple(int(rule_id) for rule_id in rule_ids),
        )
        return int(cursor.rowcount)


def delete_failed_rule(args: argparse.Namespace, table: str, rule: dict[str, Any]) -> int:
    """Delete a non-protected rule that failed during a full chain apply."""
    if int(rule.get("protected") or 0) == 1 or rule.get("id") is None:
        return 0

    with db.transaction(database_for_request(args.category, args.family)) as conn:
        cursor = db.execute_on(conn, f"DELETE FROM {table} WHERE id = ?", (int(rule["id"]),))
        return int(cursor.rowcount)


def fetch_rule(args: argparse.Namespace, table: str, rule_id: int) -> dict[str, Any]:
    """Read one enabled or disabled rule from its SQLite table."""
    columns = SELECT_COLUMNS.get(table)
    if not columns:
        raise RuntimeError(f"Unsupported rule table: {table}")

    with db.connection(database_for_request(args.category, args.family)) as conn:
        row = db.fetch_one_on(conn, f"SELECT {columns} FROM {table} WHERE id = ?", (rule_id,))

    if row is None:
        raise RuntimeError(f"Rule not found: table={table}, id={rule_id}")

    rule = db.row_to_dict(row)
    rule["family"] = args.family
    rule["table"] = table
    return rule


def rules_for_payload(args: argparse.Namespace, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve the rules affected by a work request payload."""
    table = table_from_request(args, payload)
    rule_ids = payload.get("rule_ids")

    if isinstance(payload.get("rule"), dict):
        rule = dict(payload["rule"])
        rule.setdefault("table", table)
        rule.setdefault("family", args.family)
        return [rule]

    if isinstance(rule_ids, list):
        return [fetch_rule(args, table, int(rule_id)) for rule_id in rule_ids]

    if args.target_rule_id:
        return [fetch_rule(args, table, int(args.target_rule_id))]

    if payload.get("rule_id"):
        return [fetch_rule(args, table, int(payload["rule_id"]))]

    return []


def execute_work_request(args: argparse.Namespace, payload: dict[str, Any]) -> tuple[int, int]:
    """Execute one work request and return applied and removed counts."""
    table = table_from_request(args, payload)
    rules = rules_for_payload(args, payload)
    applied = 0
    removed = 0

    if args.action_name == "apply" and isinstance(payload.get("rule_ids"), list):
        flush_chain(args, table)

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
        enforce_filter_drop_policies()

    return applied, removed


def run_action(args: argparse.Namespace) -> int:
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
        payload = payload_from_args(args)
        applied, removed = execute_work_request(args, payload)
    except Exception as exc:  # noqa: BLE001 - message is returned to workreqd.
        logger.error(f"Firewall rule execution failed: {exc}", source=LOG_SOURCE)
        return 1

    logger.log(
        f"Firewall rule execution completed: applied={applied}, removed={removed}.",
        source=LOG_SOURCE,
    )
    return 0


def main() -> int:
    """Execute a single dispatched firewall work request."""
    parser = argparse.ArgumentParser(description="HomeFirewall firewall rule executor.")
    parser.add_argument("--work-request-id")
    parser.add_argument("--request-uid")
    parser.add_argument("--category-name")
    parser.add_argument("--category")
    parser.add_argument("--family")
    parser.add_argument("--target-name")
    parser.add_argument("--action-name")
    parser.add_argument("--target-rule-id")
    parser.add_argument("--payload-json")
    args = parser.parse_args()

    if not args.work_request_id:
        logger.error("Missing --work-request-id for one-shot firewall execution.", source=LOG_SOURCE)
        return 2
    
    return run_action(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.error("Firewall rule execution interrupted.", source=LOG_SOURCE)
        raise SystemExit(0)
