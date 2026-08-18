"""Work request execution flow for policy routing changes."""

from __future__ import annotations

from core import db

from .commons import normalized_ids
from .constants import POLICY_DB_PATH
from .models import Payload, RoutingTableRow
from .routes import (
    apply_route,
    fetch_route,
    fetch_routes_for_table,
    mark_routes_applied,
    purge_routes,
    remove_route,
)
from .rules import (
    apply_rule,
    fetch_rule,
    fetch_rules_for_table,
    mark_rules_applied,
    purge_rules,
    remove_rule,
)
from .tables import (
    apply_table,
    assert_table_has_no_references,
    fetch_table,
    mark_tables_applied,
    purge_tables,
    remove_table,
)


def remove_table_dependencies(conn: db.Connection, table: RoutingTableRow) -> int:
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


def discard_failed_routes(payload: Payload) -> int:
    """Remove routes that could not be applied and undo any partial OS changes."""
    route_ids = normalized_ids(payload, "route_ids")
    if not route_ids:
        return 0

    with db.transaction(POLICY_DB_PATH) as conn:
        routes = []
        for route_id in route_ids:
            try:
                routes.append(fetch_route(conn, route_id))
            except RuntimeError:
                continue
        for route in routes:
            remove_route(route)
        return purge_routes(conn, [int(route["id"]) for route in routes])


def execute_work_request(payload: Payload) -> tuple[int, int]:
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
