#!/usr/bin/env python3
"""One-shot policy routing executor used by the work request daemon."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import db
from core.constants import DB_DIR
from core import log as logger
from core.workrequest import decode_payload

POLICY_DB_PATH = DB_DIR / "policy-routing.db"
RT_TABLES_PATH = Path("/etc/iproute2/rt_tables")
LOG_SOURCE = "proutes.py"
PROTECTED_ROUTE_TABLE_IDS = {253, 255}
PROTECTED_ROUTING_TABLE_IDS = {253, 254, 255}
PROTECTED_RULE_PRIORITIES = {0, 32766, 32767}
BASE_RT_TABLES = {
    255: "local",
    254: "main",
    253: "default",
    0: "unspec",
}


def verify_policy_database() -> None:
    """Verify that the policy routing database can be opened."""
    with db.connection(POLICY_DB_PATH) as conn:
        db.fetch_one_on(conn, "SELECT 1")


def ip_family_arg(family: str) -> str:
    """Return the iproute2 family flag."""
    return "-6" if family.upper() == "IPV6" else "-4"


def route_is_immutable(route: dict[str, Any]) -> bool:
    """Return whether a route is protected from GUI changes."""
    return int(route.get("protected") or 0) == 1 or int(route.get("table_id") or 0) in PROTECTED_ROUTE_TABLE_IDS


def table_is_immutable(table: dict[str, Any]) -> bool:
    """Return whether a routing table registry entry is protected from GUI changes."""
    return int(table.get("protected") or 0) == 1 or int(table.get("table_id") or 0) in PROTECTED_ROUTING_TABLE_IDS


def rule_is_immutable(rule: dict[str, Any]) -> bool:
    """Return whether a routing rule is protected from GUI changes."""
    return int(rule.get("protected") or 0) == 1 or int(rule.get("priority") or -1) in PROTECTED_RULE_PRIORITIES


def normalized_ids(payload: dict[str, Any], key: str) -> list[int]:
    """Return a normalized list of integer ids from the payload."""
    values = payload.get(key)
    if not isinstance(values, list):
        return []
    return [int(value) for value in values]


def fetch_table(conn: db.Connection, table_row_id: int) -> dict[str, Any]:
    """Return one routing table row from SQLite."""
    row = db.fetch_one_on(
        conn,
        """
        SELECT id, table_id, table_name, description, protected, enabled,
               applied, pending_delete
        FROM routing_tables
        WHERE id = ?
        """,
        (table_row_id,),
    )
    if row is None:
        raise RuntimeError(f"Routing table not found: id={table_row_id}")
    return db.row_to_dict(row)


def fetch_route(conn: db.Connection, route_id: int) -> dict[str, Any]:
    """Return one route row from SQLite."""
    row = db.fetch_one_on(
        conn,
        """
        SELECT id, route_order, addr_family, table_id, route_type, destination,
               gateway, dev, preferred_source, metric, scope, protocol, onlink,
               protected, enabled, applied, pending_delete
        FROM routes
        WHERE id = ?
        """,
        (route_id,),
    )
    if row is None:
        raise RuntimeError(f"Route not found: id={route_id}")
    return db.row_to_dict(row)


def fetch_rule(conn: db.Connection, rule_id: int) -> dict[str, Any]:
    """Return one policy routing rule row from SQLite."""
    row = db.fetch_one_on(
        conn,
        """
        SELECT id, rule_order, addr_family, priority, source_addr, destination_addr,
               incoming_iface, outgoing_iface, fwmark, fwmask, tos, dsfield,
               ip_proto, sport, dport, uid_range, action, table_id,
               suppress_prefixlength, suppress_ifgroup, realms, goto_priority,
               protected, enabled, applied, pending_delete
        FROM routing_rules
        WHERE id = ?
        """,
        (rule_id,),
    )
    if row is None:
        raise RuntimeError(f"Routing rule not found: id={rule_id}")
    return db.row_to_dict(row)


def fetch_routes_for_table(conn: db.Connection, table_id: int) -> list[dict[str, Any]]:
    """Return all route rows that reference one routing table."""
    return db.fetch_all_on(
        conn,
        """
        SELECT id, route_order, addr_family, table_id, route_type, destination,
               gateway, dev, preferred_source, metric, scope, protocol, onlink,
               protected, enabled, applied, pending_delete
        FROM routes
        WHERE table_id = ?
        ORDER BY id
        """,
        (table_id,),
    )


def fetch_rules_for_table(conn: db.Connection, table_id: int) -> list[dict[str, Any]]:
    """Return all policy routing rule rows that reference one routing table."""
    return db.fetch_all_on(
        conn,
        """
        SELECT id, rule_order, addr_family, priority, source_addr, destination_addr,
               incoming_iface, outgoing_iface, fwmark, fwmask, tos, dsfield,
               ip_proto, sport, dport, uid_range, action, table_id,
               suppress_prefixlength, suppress_ifgroup, realms, goto_priority,
               protected, enabled, applied, pending_delete
        FROM routing_rules
        WHERE table_id = ?
        ORDER BY id
        """,
        (table_id,),
    )


def add_if_value(command: list[str], keyword: str, value: Any) -> None:
    """Append an iproute2 keyword and value when present."""
    if value is None:
        return
    text = str(value).strip()
    if text:
        command.extend([keyword, text])


def route_spec(route: dict[str, Any]) -> list[str]:
    """Build an iproute2 route specification without the operation."""
    route_type = str(route.get("route_type") or "unicast").strip()
    destination = str(route.get("destination") or "default").strip()
    command: list[str] = []

    if route_type and route_type != "unicast":
        command.append(route_type)
    command.append(destination)
    command.extend(["table", str(route["table_id"])])

    add_if_value(command, "via", route.get("gateway"))
    add_if_value(command, "dev", route.get("dev"))
    add_if_value(command, "src", route.get("preferred_source"))
    add_if_value(command, "metric", route.get("metric"))
    add_if_value(command, "scope", route.get("scope"))
    add_if_value(command, "proto", route.get("protocol"))
    if int(route.get("onlink") or 0) == 1:
        command.append("onlink")

    return command


def rule_spec(rule: dict[str, Any]) -> list[str]:
    """Build an iproute2 rule specification without the operation."""
    command = ["priority", str(rule["priority"])]

    add_if_value(command, "from", rule.get("source_addr"))
    add_if_value(command, "to", rule.get("destination_addr"))
    add_if_value(command, "iif", rule.get("incoming_iface"))
    add_if_value(command, "oif", rule.get("outgoing_iface"))

    fwmark = rule.get("fwmark")
    if fwmark:
        mark = str(fwmark).strip()
        if rule.get("fwmask"):
            mark = f"{mark}/{rule['fwmask']}"
        command.extend(["fwmark", mark])

    add_if_value(command, "tos", rule.get("tos") or rule.get("dsfield"))
    add_if_value(command, "ipproto", rule.get("ip_proto"))
    add_if_value(command, "sport", rule.get("sport"))
    add_if_value(command, "dport", rule.get("dport"))
    add_if_value(command, "uidrange", rule.get("uid_range"))

    action = str(rule.get("action") or "lookup").strip()
    if action == "lookup":
        command.extend(["lookup", str(rule["table_id"])])
    else:
        command.append(action)

    add_if_value(command, "suppress_prefixlength", rule.get("suppress_prefixlength"))
    add_if_value(command, "suppress_ifgroup", rule.get("suppress_ifgroup"))
    add_if_value(command, "realms", rule.get("realms"))
    add_if_value(command, "goto", rule.get("goto_priority"))

    return command


def run_command(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run one iproute2 command and optionally raise with stderr on failure."""
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if check and completed.returncode != 0:
        rendered = " ".join(command)
        message = (completed.stderr or completed.stdout or "command failed").strip()
        raise RuntimeError(f"{rendered}: {message}")
    return completed


def rt_table_line_matches(line: str, table: dict[str, Any]) -> bool:
    """Return whether a line from rt_tables matches a table id or name."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    parts = stripped.split()
    if len(parts) < 2:
        return False
    return parts[0] == str(table["table_id"]) or parts[1] == str(table["table_name"])


def write_rt_tables(lines: list[str]) -> None:
    """Persist rt_tables content atomically enough for this small registry file."""
    RT_TABLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    temp_path = RT_TABLES_PATH.with_name(f".{RT_TABLES_PATH.name}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(RT_TABLES_PATH)


def ensure_base_rt_tables() -> None:
    """Ensure the iproute2 routing table registry exists with built-in tables."""
    lines = RT_TABLES_PATH.read_text(encoding="utf-8").splitlines(keepends=True) if RT_TABLES_PATH.exists() else []
    for table_id, table_name in BASE_RT_TABLES.items():
        table = {"table_id": table_id, "table_name": table_name}
        lines = [line for line in lines if not rt_table_line_matches(line, table)]
        lines.append(f"{table_id}\t{table_name}\n")
    write_rt_tables(lines)


def apply_table(table: dict[str, Any]) -> int:
    """Ensure a non-protected routing table is registered in rt_tables."""
    if table_is_immutable(table):
        raise RuntimeError(f"Protected routing table cannot be changed: id={table['id']}")
    ensure_base_rt_tables()
    lines = RT_TABLES_PATH.read_text(encoding="utf-8").splitlines(keepends=True) if RT_TABLES_PATH.exists() else []
    kept = [line for line in lines if not rt_table_line_matches(line, table)]
    kept.append(f"{table['table_id']}\t{table['table_name']}\n")
    write_rt_tables(kept)
    return 1


def remove_table(table: dict[str, Any]) -> int:
    """Remove a non-protected routing table registry entry from rt_tables."""
    if table_is_immutable(table):
        raise RuntimeError(f"Protected routing table cannot be removed: id={table['id']}")
    ensure_base_rt_tables()
    if not RT_TABLES_PATH.exists():
        return 0
    lines = RT_TABLES_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if not rt_table_line_matches(line, table)]
    if len(kept) == len(lines):
        return 0
    write_rt_tables(kept)
    return len(lines) - len(kept)


def ip_command(family: str, object_name: str, operation: str, spec: list[str]) -> list[str]:
    """Build a complete iproute2 command."""
    return ["ip", ip_family_arg(family), object_name, operation, *spec]


def remove_route(route: dict[str, Any]) -> int:
    """Remove all matching operating system route copies."""
    if route_is_immutable(route):
        raise RuntimeError(f"Protected route cannot be removed: id={route['id']}")
    removed = 0
    command = ip_command(str(route["addr_family"]), "route", "del", route_spec(route))
    while True:
        completed = run_command(command, check=False)
        if completed.returncode != 0:
            break
        removed += 1
    return removed


def apply_route(route: dict[str, Any]) -> int:
    """Apply one enabled route to the operating system."""
    if route_is_immutable(route):
        raise RuntimeError(f"Protected route cannot be changed: id={route['id']}")
    run_command(ip_command(str(route["addr_family"]), "route", "replace", route_spec(route)))
    return 1


def remove_rule(rule: dict[str, Any]) -> int:
    """Remove all matching operating system policy rule copies."""
    if rule_is_immutable(rule):
        raise RuntimeError(f"Protected routing rule cannot be removed: id={rule['id']}")
    removed = 0
    command = ip_command(str(rule["addr_family"]), "rule", "del", rule_spec(rule))
    while True:
        completed = run_command(command, check=False)
        if completed.returncode != 0:
            break
        removed += 1
    return removed


def apply_rule(rule: dict[str, Any]) -> int:
    """Apply one enabled policy routing rule to the operating system."""
    if rule_is_immutable(rule):
        raise RuntimeError(f"Protected routing rule cannot be changed: id={rule['id']}")
    remove_rule(rule)
    run_command(ip_command(str(rule["addr_family"]), "rule", "add", rule_spec(rule)))
    return 1


def mark_tables_applied(conn: db.Connection, table_row_ids: list[int], enabled: int) -> None:
    """Mark routing table rows as applied after registry changes."""
    if not table_row_ids:
        return
    placeholders = ",".join("?" for _ in table_row_ids)
    db.execute_on(
        conn,
        f"""
        UPDATE routing_tables
        SET enabled = ?, applied = 1, pending_delete = 0, updated_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
        """,
        (enabled, *table_row_ids),
    )


def mark_routes_applied(conn: db.Connection, route_ids: list[int], enabled: int) -> None:
    """Mark route rows as applied after successful operating system changes."""
    if not route_ids:
        return
    placeholders = ",".join("?" for _ in route_ids)
    db.execute_on(
        conn,
        f"""
        UPDATE routes
        SET enabled = ?, applied = 1, pending_delete = 0, updated_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
        """,
        (enabled, *route_ids),
    )


def mark_rules_applied(conn: db.Connection, rule_ids: list[int], enabled: int) -> None:
    """Mark routing rule rows as applied after successful operating system changes."""
    if not rule_ids:
        return
    placeholders = ",".join("?" for _ in rule_ids)
    db.execute_on(
        conn,
        f"""
        UPDATE routing_rules
        SET enabled = ?, applied = 1, pending_delete = 0, updated_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
        """,
        (enabled, *rule_ids),
    )


def purge_tables(conn: db.Connection, table_row_ids: list[int]) -> int:
    """Delete routing table rows that were successfully removed from rt_tables."""
    if not table_row_ids:
        return 0
    placeholders = ",".join("?" for _ in table_row_ids)
    cursor = db.execute_on(conn, f"DELETE FROM routing_tables WHERE id IN ({placeholders})", tuple(table_row_ids))
    return int(cursor.rowcount)


def purge_routes(conn: db.Connection, route_ids: list[int]) -> int:
    """Delete route rows that were successfully removed from the operating system."""
    if not route_ids:
        return 0
    placeholders = ",".join("?" for _ in route_ids)
    cursor = db.execute_on(conn, f"DELETE FROM routes WHERE id IN ({placeholders})", tuple(route_ids))
    return int(cursor.rowcount)


def purge_rules(conn: db.Connection, rule_ids: list[int]) -> int:
    """Delete routing rule rows that were successfully removed from the operating system."""
    if not rule_ids:
        return 0
    placeholders = ",".join("?" for _ in rule_ids)
    cursor = db.execute_on(conn, f"DELETE FROM routing_rules WHERE id IN ({placeholders})", tuple(rule_ids))
    return int(cursor.rowcount)


def assert_table_has_no_references(conn: db.Connection, table: dict[str, Any]) -> None:
    """Fail when routes or rules still reference a routing table."""
    table_id = int(table["table_id"])
    route_row = db.fetch_one_on(conn, "SELECT COUNT(*) AS total FROM routes WHERE table_id = ?", (table_id,))
    rule_row = db.fetch_one_on(conn, "SELECT COUNT(*) AS total FROM routing_rules WHERE table_id = ?", (table_id,))
    route_count = int(route_row["total"] if route_row is not None else 0)
    rule_count = int(rule_row["total"] if rule_row is not None else 0)

    if route_count or rule_count:
        raise RuntimeError(
            "Routing table cannot be deleted while it is referenced by "
            f"{route_count} route(s) and {rule_count} routing rule(s): "
            f"{table['table_name']} ({table_id})."
        )


def remove_table_dependencies(conn: db.Connection, table: dict[str, Any]) -> int:
    """Remove non-protected routes and rules that still reference a deleted table."""
    removed = 0
    route_ids: list[int] = []
    rule_ids: list[int] = []

    for route in fetch_routes_for_table(conn, int(table["table_id"])):
        removed += remove_route(route)
        route_ids.append(int(route["id"]))
    removed += purge_routes(conn, route_ids)

    for rule in fetch_rules_for_table(conn, int(table["table_id"])):
        removed += remove_rule(rule)
        rule_ids.append(int(rule["id"]))
    removed += purge_rules(conn, rule_ids)

    return removed


def execute_work_request(payload: dict[str, Any]) -> tuple[int, int]:
    """Apply queued policy routing changes and return applied and removed counts."""
    applied = 0
    removed = 0
    table_ids = normalized_ids(payload, "table_ids")
    disable_table_ids = normalized_ids(payload, "disable_table_ids")
    delete_table_ids = normalized_ids(payload, "delete_table_ids")
    route_ids = normalized_ids(payload, "route_ids")
    rule_ids = normalized_ids(payload, "rule_ids")
    disable_route_ids = normalized_ids(payload, "disable_route_ids")
    disable_rule_ids = normalized_ids(payload, "disable_rule_ids")
    delete_route_ids = normalized_ids(payload, "delete_route_ids")
    delete_rule_ids = normalized_ids(payload, "delete_rule_ids")

    with db.transaction(POLICY_DB_PATH) as conn:
        tables_to_apply = [fetch_table(conn, table_id) for table_id in table_ids]
        tables_to_disable = [fetch_table(conn, table_id) for table_id in disable_table_ids]
        tables_to_delete = [fetch_table(conn, table_id) for table_id in delete_table_ids]
        routes_to_apply = [fetch_route(conn, route_id) for route_id in route_ids]
        rules_to_apply = [fetch_rule(conn, rule_id) for rule_id in rule_ids]
        routes_to_disable = [fetch_route(conn, route_id) for route_id in disable_route_ids]
        rules_to_disable = [fetch_rule(conn, rule_id) for rule_id in disable_rule_ids]
        routes_to_delete = [fetch_route(conn, route_id) for route_id in delete_route_ids]
        rules_to_delete = [fetch_rule(conn, rule_id) for rule_id in delete_rule_ids]

        for table in tables_to_apply:
            applied += apply_table(table)
        mark_tables_applied(conn, table_ids, 1)

        for table in tables_to_disable:
            removed += remove_table(table)
        mark_tables_applied(conn, disable_table_ids, 0)

        for route in routes_to_disable:
            removed += remove_route(route)
        mark_routes_applied(conn, disable_route_ids, 0)

        for rule in rules_to_disable:
            removed += remove_rule(rule)
        mark_rules_applied(conn, disable_rule_ids, 0)

        for route in routes_to_delete:
            removed += remove_route(route)
        removed += purge_routes(conn, delete_route_ids)

        for rule in rules_to_delete:
            removed += remove_rule(rule)
        removed += purge_rules(conn, delete_rule_ids)

        for table in tables_to_delete:
            removed += remove_table_dependencies(conn, table)
            assert_table_has_no_references(conn, table)
            removed += remove_table(table)
        removed += purge_tables(conn, delete_table_ids)

        for route in routes_to_apply:
            applied += apply_route(route)
        mark_routes_applied(conn, route_ids, 1)

        for rule in rules_to_apply:
            applied += apply_rule(rule)
        mark_rules_applied(conn, rule_ids, 1)

    return applied, removed


def run_action(args: argparse.Namespace) -> int:
    """Handle one dispatched policy routing work request."""
    if args.category != "POLICY_ROUTING":
        logger.error(f"Unsupported policy routing category: {args.category}", source=LOG_SOURCE)
        return 2

    try:
        verify_policy_database()
    except Exception as exc:  # noqa: BLE001 - message is returned to workreqd.
        logger.error(f"Could not connect to policy routing database: {exc}", source=LOG_SOURCE)
        return 1

    logger.log(
        "Received work request "
        f"id={args.work_request_id} category={args.category_name} action={args.action_name}.",
        source=LOG_SOURCE,
    )

    try:
        if args.action_name != "apply":
            raise RuntimeError(f"Unsupported policy routing action: {args.action_name}")
        payload = decode_payload(args.payload_json)
        applied, removed = execute_work_request(payload)
    except Exception as exc:  # noqa: BLE001 - message is returned to workreqd.
        logger.error(f"Policy routing execution failed: {exc}", source=LOG_SOURCE)
        return 1

    logger.log(f"Policy routing execution completed: applied={applied}, removed={removed}.", source=LOG_SOURCE)
    return 0


def main() -> int:
    """Execute a single dispatched policy routing work request."""
    parser = argparse.ArgumentParser(description="ArmFirewall policy routing executor.")
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
        logger.error("Missing --work-request-id for one-shot policy routing execution.", source=LOG_SOURCE)
        return 2

    return run_action(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.error("Policy routing execution interrupted.", source=LOG_SOURCE)
        raise SystemExit(0)
