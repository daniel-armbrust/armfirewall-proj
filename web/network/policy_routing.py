from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core import db
from core.constants import POLICY_ROUTING_DB_PATH, WORK_REQUEST_DB_PATH
from web.constants import TEMPLATE_DIR
from web.context import menu_context


templates = Jinja2Templates(directory=TEMPLATE_DIR)

POLICY_DB_PATH = POLICY_ROUTING_DB_PATH

ADDR_FAMILIES = {"ipv4", "ipv6"}
ROUTE_TYPES = {"unicast", "local", "broadcast", "multicast", "throw", "unreachable", "prohibit", "blackhole", "anycast"}
ROUTE_ACTIONS = {"lookup", "blackhole", "unreachable", "prohibit"}
PROTECTED_ROUTE_TABLE_IDS = {253, 255}


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for policy routing pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
        "menu": menu_context(),
    }


def render_policy_routing(request: Request) -> HTMLResponse:
    """Render the policy routing template."""
    ensure_policy_db()
    return templates.TemplateResponse(
        request,
        "network/policy_routing.html",
        context=page_context(request, "Policy Routing"),
    )


def ensure_policy_db() -> None:
    """Verify the installed policy-routing database before using it."""
    db.verify_database(POLICY_DB_PATH)
    with db.transaction(POLICY_DB_PATH) as conn:
        ensure_applied_columns(conn)


def ensure_applied_columns(conn: db.Connection) -> None:
    """Add apply-state columns to older policy routing databases."""
    for table in ("routing_tables", "routes", "routing_rules"):
        columns = {str(row["name"]) for row in db.fetch_all_on(conn, f"PRAGMA table_info({table})")}
        if "applied" not in columns:
            db.execute_on(conn, f"ALTER TABLE {table} ADD COLUMN applied INTEGER NOT NULL DEFAULT 0")


def normalize_family(value: Any) -> str:
    """Normalize and validate an address family."""
    family = str(value or "ipv4").strip().lower()
    if family not in ADDR_FAMILIES:
        raise HTTPException(status_code=400, detail="addr_family must be ipv4 or ipv6.")
    return family


def normalize_enabled(value: Any) -> int:
    """Convert an enabled value to a SQLite flag."""
    return 1 if str(value).lower() in {"1", "true", "yes", "on"} else 0


def optional_int(value: Any) -> int | None:
    """Convert an optional numeric value to int."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid integer value: {value}") from exc


def optional_text(value: Any) -> str | None:
    """Return a stripped optional string."""
    text = str(value or "").strip()
    return text or None


def next_order(conn: db.Connection, table: str, column: str) -> int:
    """Return the next display order for a table."""
    row = db.fetch_one_on(conn, f"SELECT COALESCE(MAX({column}), 0) + 1 AS next_order FROM {table}")
    return int(row["next_order"] if row is not None else 1)


def row_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLite row-like value to a dictionary."""
    return db.row_to_dict(row)


def table_id_is_immutable(table_id: Any) -> bool:
    """Return whether a Linux routing table is managed as read-only."""
    try:
        return int(table_id) in PROTECTED_ROUTE_TABLE_IDS
    except (TypeError, ValueError):
        return False


def row_value(row: Any, key: str) -> Any:
    """Return a row value when the selected column exists."""
    return row[key] if row is not None and key in row.keys() else None


def policy_item_is_immutable(conn: db.Connection, table: str, item_id: int) -> bool:
    """Return whether a policy routing item cannot be changed by the GUI."""
    if table == "routes":
        current = db.fetch_one_on(conn, "SELECT protected, table_id FROM routes WHERE id = ?", (item_id,))
    elif table == "routing_tables":
        current = db.fetch_one_on(conn, "SELECT protected, table_id FROM routing_tables WHERE id = ?", (item_id,))
    else:
        current = db.fetch_one_on(conn, f"SELECT protected FROM {table} WHERE id = ?", (item_id,))
    if current is None:
        raise HTTPException(status_code=404, detail="Policy routing item not found.")
    return int(current["protected"]) == 1 or table_id_is_immutable(row_value(current, "table_id"))


def get_tables() -> list[dict[str, Any]]:
    """Return persisted policy routing tables."""
    ensure_policy_db()
    with db.connection(POLICY_DB_PATH) as conn:
        return db.fetch_all_on(
            conn,
            """
            SELECT id, table_id, table_name, description, protected, enabled, applied,
                   pending_delete, created_at, updated_at
            FROM routing_tables
            ORDER BY table_id
            """,
        )


def get_routes() -> list[dict[str, Any]]:
    """Return persisted policy routes."""
    ensure_policy_db()
    with db.connection(POLICY_DB_PATH) as conn:
        return db.fetch_all_on(
            conn,
            """
            SELECT r.id, r.route_order, r.addr_family, r.table_id, t.table_name,
                   r.route_type, r.destination, r.gateway, r.dev, r.preferred_source,
                   r.metric, r.scope, r.protocol, r.onlink, r.protected, r.enabled,
                   r.applied, r.pending_delete, r.created_at, r.updated_at
            FROM routes r
            JOIN routing_tables t ON t.table_id = r.table_id
            ORDER BY r.addr_family, r.table_id, r.route_order, r.id
            """,
        )


def get_rules() -> list[dict[str, Any]]:
    """Return persisted policy routing rules."""
    ensure_policy_db()
    with db.connection(POLICY_DB_PATH) as conn:
        return db.fetch_all_on(
            conn,
            """
            SELECT rr.id, rr.rule_order, rr.addr_family, rr.priority,
                   rr.source_addr, rr.destination_addr, rr.incoming_iface,
                   rr.outgoing_iface, rr.fwmark, rr.fwmask, rr.tos, rr.dsfield,
                   rr.ip_proto, rr.sport, rr.dport, rr.uid_range, rr.action,
                   rr.table_id, t.table_name, rr.suppress_prefixlength,
                   rr.suppress_ifgroup, rr.realms, rr.goto_priority,
                   rr.protected, rr.enabled, rr.applied, rr.pending_delete,
                   rr.created_at, rr.updated_at
            FROM routing_rules rr
            LEFT JOIN routing_tables t ON t.table_id = rr.table_id
            ORDER BY rr.addr_family, rr.priority, rr.id
            """,
        )


def get_policy_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent work requests for policy routing."""
    query = """
        SELECT id, request_uid, status, source, category_name, action_name,
               target_rule_id, error_message, created_at, updated_at
        FROM work_requests
        WHERE category_name LIKE 'POLICY_ROUTING.%'
        ORDER BY id DESC
        LIMIT ?
    """
    with db.connection(WORK_REQUEST_DB_PATH) as conn:
        rows = db.fetch_all_on(conn, query, (limit,))
    return {"requests": rows}


def get_policy_routing() -> dict[str, Any]:
    """Return all policy routing data used by the frontend."""
    tables = get_tables()
    routes = get_routes()
    rules = get_rules()
    enabled_routes = sum(1 for route in routes if int(route["enabled"]) == 1)
    enabled_rules = sum(1 for rule in rules if int(rule["enabled"]) == 1)
    return {
        "summary": {
            "tables": len(tables),
            "routes": len(routes),
            "rules": len(rules),
            "enabled": enabled_routes + enabled_rules,
        },
        "tables": tables,
        "routes": routes,
        "rules": rules,
    }


def sanitize_table_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a routing table payload."""
    table_id = optional_int(payload.get("table_id"))
    table_name = str(payload.get("table_name") or "").strip()
    if table_id is None or table_id <= 0:
        raise HTTPException(status_code=400, detail="table_id must be a positive integer.")
    if table_id_is_immutable(table_id):
        raise HTTPException(status_code=403, detail="Protected routing tables cannot be changed.")
    if not table_name:
        raise HTTPException(status_code=400, detail="table_name is required.")
    return {
        "table_id": table_id,
        "table_name": table_name,
        "description": optional_text(payload.get("description")),
        "enabled": normalize_enabled(payload.get("enabled", 1)),
        "protected": 0,
    }


def sanitize_route_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an ip route payload."""
    family = normalize_family(payload.get("addr_family"))
    table_id = optional_int(payload.get("table_id"))
    route_type = str(payload.get("route_type") or "unicast").strip().lower()
    if route_type not in ROUTE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported route type.")
    if table_id is None:
        raise HTTPException(status_code=400, detail="table_id is required.")
    if table_id_is_immutable(table_id):
        raise HTTPException(status_code=403, detail="Protected routing tables cannot receive GUI routes.")
    return {
        "addr_family": family,
        "table_id": table_id,
        "route_type": route_type,
        "destination": str(payload.get("destination") or "default").strip(),
        "gateway": optional_text(payload.get("gateway")),
        "dev": optional_text(payload.get("dev")),
        "preferred_source": optional_text(payload.get("preferred_source")),
        "metric": optional_int(payload.get("metric")),
        "scope": optional_text(payload.get("scope")),
        "protocol": optional_text(payload.get("protocol")),
        "onlink": normalize_enabled(payload.get("onlink", 0)),
        "enabled": normalize_enabled(payload.get("enabled", 1)),
        "protected": 0,
    }


def sanitize_rule_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an ip rule payload."""
    family = normalize_family(payload.get("addr_family"))
    priority = optional_int(payload.get("priority"))
    action = str(payload.get("action") or "lookup").strip().lower()
    table_id = optional_int(payload.get("table_id"))
    if priority is None:
        raise HTTPException(status_code=400, detail="priority is required.")
    if action not in ROUTE_ACTIONS:
        raise HTTPException(status_code=400, detail="Unsupported routing rule action.")
    if action == "lookup" and table_id is None:
        raise HTTPException(status_code=400, detail="table_id is required when action is lookup.")
    if action == "lookup" and table_id_is_immutable(table_id):
        raise HTTPException(status_code=403, detail="Protected routing tables cannot receive GUI routing rules.")
    if action != "lookup":
        table_id = None
    return {
        "addr_family": family,
        "priority": priority,
        "source_addr": optional_text(payload.get("source_addr")),
        "destination_addr": optional_text(payload.get("destination_addr")),
        "incoming_iface": optional_text(payload.get("incoming_iface")),
        "outgoing_iface": optional_text(payload.get("outgoing_iface")),
        "fwmark": optional_text(payload.get("fwmark")),
        "fwmask": optional_text(payload.get("fwmask")),
        "tos": optional_text(payload.get("tos")),
        "ip_proto": optional_text(payload.get("ip_proto")),
        "sport": optional_text(payload.get("sport")),
        "dport": optional_text(payload.get("dport")),
        "uid_range": optional_text(payload.get("uid_range")),
        "action": action,
        "table_id": table_id,
        "enabled": normalize_enabled(payload.get("enabled", 1)),
        "protected": 0,
    }


def create_routing_table(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a routing table entry and queue rt_tables synchronization."""
    ensure_policy_db()
    item = sanitize_table_payload(payload)
    with db.transaction(POLICY_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO routing_tables (
                table_id, table_name, description, protected, enabled, applied,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (item["table_id"], item["table_name"], item["description"], item["protected"], item["enabled"]),
        )
        table_row_id = int(cursor.lastrowid)

    work_request_id = enqueue_policy_work_request(
        "ipv4",
        {
            "family": "ipv4",
            "table_ids": [table_row_id] if item["enabled"] == 1 else [],
            "disable_table_ids": [table_row_id] if item["enabled"] == 0 else [],
            "delete_table_ids": [],
            "route_ids": [],
            "rule_ids": [],
            "disable_route_ids": [],
            "disable_rule_ids": [],
            "delete_route_ids": [],
            "delete_rule_ids": [],
        },
    )
    return {"table_row_id": table_row_id, "work_request_id": work_request_id, "status": "queued"}


def create_route(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a route entry and queue its operating system application."""
    ensure_policy_db()
    item = sanitize_route_payload(payload)
    with db.transaction(POLICY_DB_PATH) as conn:
        order = next_order(conn, "routes", "route_order")
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO routes (
                route_order, addr_family, table_id, route_type, destination,
                gateway, dev, preferred_source, metric, scope, protocol, onlink,
                protected, enabled, applied, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                order, item["addr_family"], item["table_id"], item["route_type"], item["destination"],
                item["gateway"], item["dev"], item["preferred_source"], item["metric"], item["scope"],
                item["protocol"], item["onlink"], item["protected"], item["enabled"],
            ),
        )
    route_id = int(cursor.lastrowid)
    work_request_id = enqueue_policy_work_request(
        item["addr_family"],
        policy_work_request_payload(
            item["addr_family"],
            table_ids=pending_table_ids(item["table_id"]),
            route_ids=[route_id] if item["enabled"] == 1 else [],
            disable_route_ids=[route_id] if item["enabled"] == 0 else [],
        ),
    )
    return {"route_id": route_id, "work_request_id": work_request_id, "status": "queued"}


def create_rule(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a routing rule entry and queue its operating system application."""
    ensure_policy_db()
    item = sanitize_rule_payload(payload)
    with db.transaction(POLICY_DB_PATH) as conn:
        order = next_order(conn, "routing_rules", "rule_order")
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO routing_rules (
                rule_order, addr_family, priority, source_addr, destination_addr,
                incoming_iface, outgoing_iface, fwmark, fwmask, tos, ip_proto,
                sport, dport, uid_range, action, table_id, protected, enabled,
                applied, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                order, item["addr_family"], item["priority"], item["source_addr"], item["destination_addr"],
                item["incoming_iface"], item["outgoing_iface"], item["fwmark"], item["fwmask"], item["tos"],
                item["ip_proto"], item["sport"], item["dport"], item["uid_range"], item["action"],
                item["table_id"], item["protected"], item["enabled"],
            ),
        )
    rule_id = int(cursor.lastrowid)
    table_ids = pending_table_ids(item["table_id"]) if item["action"] == "lookup" and item["table_id"] is not None else []
    work_request_id = enqueue_policy_work_request(
        item["addr_family"],
        policy_work_request_payload(
            item["addr_family"],
            table_ids=table_ids,
            rule_ids=[rule_id] if item["enabled"] == 1 else [],
            disable_rule_ids=[rule_id] if item["enabled"] == 0 else [],
        ),
    )
    return {"rule_id": rule_id, "work_request_id": work_request_id, "status": "queued"}


def mark_pending_delete(table: str, item_id: int) -> dict[str, Any]:
    """Queue one policy routing item for deletion from the operating system."""
    ensure_policy_db()
    if table not in {"routes", "routing_rules", "routing_tables"}:
        raise HTTPException(status_code=400, detail="Unsupported policy routing table.")
    with db.transaction(POLICY_DB_PATH) as conn:
        if policy_item_is_immutable(conn, table, item_id):
            raise HTTPException(status_code=403, detail="Protected policy routing items cannot be deleted.")
        if table == "routes":
            current = db.fetch_one_on(conn, "SELECT addr_family FROM routes WHERE id = ?", (item_id,))
        elif table == "routing_rules":
            current = db.fetch_one_on(conn, "SELECT addr_family FROM routing_rules WHERE id = ?", (item_id,))
        else:
            current = db.fetch_one_on(conn, "SELECT id FROM routing_tables WHERE id = ?", (item_id,))
        if current is None:
            raise HTTPException(status_code=404, detail="Policy routing item not found.")
        db.execute_on(conn, f"UPDATE {table} SET pending_delete = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (item_id,))

    family = str(current["addr_family"]) if table != "routing_tables" else "ipv4"
    payload_key = {
        "routes": "delete_route_ids",
        "routing_rules": "delete_rule_ids",
        "routing_tables": "delete_table_ids",
    }[table]
    work_request_id = enqueue_policy_work_request(
        family,
        policy_work_request_payload(family, **{payload_key: [item_id]}),
    )
    return {"item_id": item_id, "work_request_id": work_request_id, "status": "queued"}


def set_enabled(table: str, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Enable or disable a policy routing item without applying it."""
    ensure_policy_db()
    if table not in {"routes", "routing_rules", "routing_tables"}:
        raise HTTPException(status_code=400, detail="Unsupported policy routing table.")
    enabled = normalize_enabled(payload.get("enabled", 0))
    with db.transaction(POLICY_DB_PATH) as conn:
        if table == "routes":
            current = db.fetch_one_on(conn, "SELECT protected, pending_delete, table_id FROM routes WHERE id = ?", (item_id,))
        elif table == "routing_tables":
            current = db.fetch_one_on(conn, "SELECT protected, pending_delete, table_id FROM routing_tables WHERE id = ?", (item_id,))
        else:
            current = db.fetch_one_on(conn, f"SELECT protected, pending_delete FROM {table} WHERE id = ?", (item_id,))
        if current is None:
            raise HTTPException(status_code=404, detail="Policy routing item not found.")
        if int(current["pending_delete"]) == 1:
            raise HTTPException(status_code=403, detail="Policy routing items pending deletion cannot be changed.")
        if int(current["protected"]) == 1 or table_id_is_immutable(row_value(current, "table_id")):
            raise HTTPException(status_code=403, detail="Protected policy routing items cannot be changed.")
        db.execute_on(conn, f"UPDATE {table} SET enabled = ?, applied = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (enabled, item_id))
    return {"item_id": item_id, "enabled": enabled, "status": "saved"}


def ensure_work_request_category(family: str) -> str:
    """Ensure a work request category exists for policy routing."""
    category_name = f"POLICY_ROUTING.{family.upper()}.main"
    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            INSERT OR IGNORE INTO work_request_categories (
                name, category, family, target_name, description
            ) VALUES (?, 'POLICY_ROUTING', ?, 'main', ?)
            """,
            (category_name, family.upper(), f"{family.upper()} policy routing changes."),
        )
    return category_name


def enqueue_policy_work_request(family: str, payload: dict[str, Any]) -> int:
    """Queue a policy routing work request."""
    category_name = ensure_work_request_category(family)
    request_uid = str(uuid.uuid4())
    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, payload_json, status
            ) VALUES (?, 'gui', ?, 'apply', NULL, ?, 'queue')
            """,
            (request_uid, category_name, json.dumps(payload, sort_keys=True)),
        )
        request_id = int(cursor.lastrowid)
        db.execute_on(
            conn,
            """
            INSERT INTO work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', ?)
            """,
            (request_id, f"Queued apply for {category_name}."),
        )
    return request_id


def policy_work_request_payload(family: str, **items: list[int]) -> dict[str, Any]:
    """Build a complete Policy Routing apply payload for one address family."""
    payload: dict[str, Any] = {
        "family": family,
        "table_ids": [],
        "disable_table_ids": [],
        "delete_table_ids": [],
        "route_ids": [],
        "rule_ids": [],
        "disable_route_ids": [],
        "disable_rule_ids": [],
        "delete_route_ids": [],
        "delete_rule_ids": [],
    }
    payload.update(items)
    return payload


def pending_table_ids(table_id: int) -> list[int]:
    """Return an unapplied routing table row that must precede a route or rule."""
    with db.connection(POLICY_DB_PATH) as conn:
        row = db.fetch_one_on(
            conn,
            """
            SELECT id, enabled, applied, pending_delete
            FROM routing_tables
            WHERE table_id = ?
            """,
            (table_id,),
        )
    if row is None:
        raise HTTPException(status_code=400, detail="The selected routing table does not exist.")
    if int(row["enabled"]) != 1 or int(row["pending_delete"]) == 1:
        raise HTTPException(status_code=400, detail="The selected routing table is not enabled.")
    return [int(row["id"])] if int(row["applied"]) == 0 else []


def apply_policy_routing() -> dict[str, Any]:
    """Queue policy routing changes for IPv4 and IPv6."""
    ensure_policy_db()
    work_requests = []
    data = get_policy_routing()
    for family in ("ipv4", "ipv6"):
        table_ids = [int(table["id"]) for table in data["tables"] if family == "ipv4" and int(table["enabled"]) == 1 and int(table["applied"]) == 0 and int(table["pending_delete"]) == 0]
        disable_table_ids = [int(table["id"]) for table in data["tables"] if family == "ipv4" and int(table["enabled"]) == 0 and int(table["applied"]) == 0 and int(table["pending_delete"]) == 0]
        delete_table_ids = [int(table["id"]) for table in data["tables"] if family == "ipv4" and int(table["pending_delete"]) == 1]
        route_ids = [int(route["id"]) for route in data["routes"] if route["addr_family"] == family and int(route["enabled"]) == 1 and int(route["applied"]) == 0 and int(route["pending_delete"]) == 0]
        rule_ids = [int(rule["id"]) for rule in data["rules"] if rule["addr_family"] == family and int(rule["enabled"]) == 1 and int(rule["applied"]) == 0 and int(rule["pending_delete"]) == 0]
        disable_route_ids = [int(route["id"]) for route in data["routes"] if route["addr_family"] == family and int(route["enabled"]) == 0 and int(route["applied"]) == 0 and int(route["pending_delete"]) == 0]
        disable_rule_ids = [int(rule["id"]) for rule in data["rules"] if rule["addr_family"] == family and int(rule["enabled"]) == 0 and int(rule["applied"]) == 0 and int(rule["pending_delete"]) == 0]
        delete_route_ids = [int(route["id"]) for route in data["routes"] if route["addr_family"] == family and int(route["pending_delete"]) == 1]
        delete_rule_ids = [int(rule["id"]) for rule in data["rules"] if rule["addr_family"] == family and int(rule["pending_delete"]) == 1]
        if not table_ids and not disable_table_ids and not delete_table_ids and not route_ids and not rule_ids and not disable_route_ids and not disable_rule_ids and not delete_route_ids and not delete_rule_ids:
            continue
        payload = {
            "family": family,
            "table_ids": table_ids,
            "disable_table_ids": disable_table_ids,
            "delete_table_ids": delete_table_ids,
            "route_ids": route_ids,
            "rule_ids": rule_ids,
            "disable_route_ids": disable_route_ids,
            "disable_rule_ids": disable_rule_ids,
            "delete_route_ids": delete_route_ids,
            "delete_rule_ids": delete_rule_ids,
        }
        work_request_id = enqueue_policy_work_request(family, payload)
        work_requests.append({"family": family, "work_request_id": work_request_id, "payload": payload})
    return {"work_requests": work_requests, "work_request_count": len(work_requests)}
