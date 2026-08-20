"""Route operations for the policy routing executor."""

from __future__ import annotations

from core import db
from core.process import run_command

from .commons import add_if_value, ip_family_arg
from .constants import PROTECTED_ROUTE_TABLE_IDS
from .models import RouteRow


def route_is_immutable(route: RouteRow) -> bool:
    """Return whether a route is protected from GUI changes."""
    return int(route.get("protected") or 0) == 1 or int(route.get("table_id") or 0) in PROTECTED_ROUTE_TABLE_IDS


def fetch_route(conn: db.Connection, route_id: int) -> RouteRow:
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


def fetch_routes_for_table(conn: db.Connection, table_id: int) -> list[RouteRow]:
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


def route_spec(route: RouteRow) -> list[str]:
    """Build an iproute2 route specification without the operation."""
    route_type = str(route.get("route_type") or "unicast").strip()
    destination = str(route.get("destination") or "default").strip()
    command: list[str] = []

    if route_type and route_type != "unicast":
        command.append(route_type)
    
    command.append(destination)
    command.extend(["table", str(route["table_id"])])

    gateway = route.get("gateway")
    add_if_value(command, "via", gateway)
    add_if_value(command, "dev", route.get("dev"))
    add_if_value(command, "src", route.get("preferred_source"))
    add_if_value(command, "metric", route.get("metric"))
    add_if_value(command, "scope", route.get("scope"))
    add_if_value(command, "proto", route.get("protocol"))

    # Allow a configured next hop even when it is outside a directly connected subnet.
    if gateway:
        command.append("onlink")

    return command


def ip_command(family: str, object_name: str, operation: str, spec: list[str]) -> list[str]:
    """Build a complete iproute2 command."""
    return ["ip", ip_family_arg(family), object_name, operation, *spec]


def remove_route(route: RouteRow) -> int:
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


def apply_route(route: RouteRow) -> int:
    """Apply one enabled route to the operating system."""
    if route_is_immutable(route):
        raise RuntimeError(f"Protected route cannot be changed: id={route['id']}")
    
    run_command(ip_command(str(route["addr_family"]), "route", "replace", route_spec(route)))
    
    return 1


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


def purge_routes(conn: db.Connection, route_ids: list[int]) -> int:
    """Delete route rows that were successfully removed from the operating system."""
    if not route_ids:
        return 0
    
    placeholders = ",".join("?" for _ in route_ids)
    cursor = db.execute_on(conn, f"DELETE FROM routes WHERE id IN ({placeholders})", tuple(route_ids))
    
    return int(cursor.rowcount)
