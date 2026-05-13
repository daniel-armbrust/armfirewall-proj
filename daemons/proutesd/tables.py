"""Routing table registry operations for the policy routing executor."""

from __future__ import annotations

from core import db

from .constants import BASE_RT_TABLES, PROTECTED_ROUTING_TABLE_IDS, RT_TABLES_PATH
from .models import RoutingTableRow


def table_is_immutable(table: RoutingTableRow) -> bool:
    """Return whether a routing table registry entry is protected from GUI changes."""
    return int(table.get("protected") or 0) == 1 or int(table.get("table_id") or 0) in PROTECTED_ROUTING_TABLE_IDS


def fetch_table(conn: db.Connection, table_row_id: int) -> RoutingTableRow:
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


def rt_table_line_matches(line: str, table: RoutingTableRow) -> bool:
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


def apply_table(table: RoutingTableRow) -> int:
    """Ensure a non-protected routing table is registered in rt_tables."""
    if table_is_immutable(table):
        raise RuntimeError(f"Protected routing table cannot be changed: id={table['id']}")
    
    ensure_base_rt_tables()
    lines = RT_TABLES_PATH.read_text(encoding="utf-8").splitlines(keepends=True) if RT_TABLES_PATH.exists() else []
    kept = [line for line in lines if not rt_table_line_matches(line, table)]
    kept.append(f"{table['table_id']}\t{table['table_name']}\n")
    write_rt_tables(kept)
    
    return 1


def remove_table(table: RoutingTableRow) -> int:
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


def purge_tables(conn: db.Connection, table_row_ids: list[int]) -> int:
    """Delete routing table rows that were successfully removed from rt_tables."""
    if not table_row_ids:
        return 0
    
    placeholders = ",".join("?" for _ in table_row_ids)
    cursor = db.execute_on(conn, f"DELETE FROM routing_tables WHERE id IN ({placeholders})", tuple(table_row_ids))
    
    return int(cursor.rowcount)


def assert_table_has_no_references(conn: db.Connection, table: RoutingTableRow) -> None:
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
