"""SQLite persistence for BIRD diagnostic snapshots."""

from __future__ import annotations

from core import db
from core.constants import COLLECTORD_BIRD_COMMAND_RETENTION

from .models import BirdRouteRow


RIP_ROUTE_TABLES = ("rip_imported_routes", "rip_exported_routes")


def insert_command_run(conn: db.Connection, command_text: str, completed, duration_ms: int) -> int:
    """Persist one diagnostic command execution."""
    cursor = db.execute_on(
        conn,
        """INSERT INTO diagnostic_command_run (command, exit_code, stdout, stderr, duration_ms)
           VALUES (?, ?, ?, ?, ?)""",
        (command_text, completed.returncode, completed.stdout, completed.stderr, duration_ms),
    )
    return int(cursor.lastrowid)


def insert_protocol_rows(conn: db.Connection, command_id: int, rows) -> None:
    """Persist parsed protocol rows for one command run."""
    db.executemany_on(
        conn,
        """INSERT INTO diagnostic_protocol (
               command_id, name, proto, table_name, state, since, info, raw_line
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(command_id, row.name, row.proto, row.table_name, row.state, row.since, row.info, row.raw_line) for row in rows],
    )


def ensure_rip_route_tables(conn: db.Connection) -> None:
    """Create structured RIP route tables for upgraded installations."""
    for table_name in RIP_ROUTE_TABLES:
        db.execute_on(conn, f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT, command_id INTEGER NOT NULL,
                table_name TEXT, route_prefix TEXT NOT NULL, route_type TEXT,
                source_protocol TEXT, since TEXT,
                selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
                metric INTEGER, next_hop TEXT, iface_name TEXT, raw_route TEXT NOT NULL,
                raw_detail TEXT, collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (command_id) REFERENCES diagnostic_command_run(id) ON DELETE CASCADE
            )""")
        columns = {row["name"] for row in db.fetch_all_on(conn, f"PRAGMA table_info({table_name})")}
        if "table_name" not in columns:
            db.execute_on(conn, f"ALTER TABLE {table_name} ADD COLUMN table_name TEXT")
        db.execute_on(conn, f"CREATE INDEX IF NOT EXISTS idx_bird_{table_name}_command ON {table_name} (command_id)")
        db.execute_on(conn, f"CREATE INDEX IF NOT EXISTS idx_bird_{table_name}_prefix ON {table_name} (route_prefix)")
        db.execute_on(conn, f"CREATE INDEX IF NOT EXISTS idx_bird_{table_name}_table_name ON {table_name} (table_name)")


def rip_protocol_enabled(conn: db.Connection) -> bool:
    """Return whether the persisted RIP protocol is enabled."""
    row = db.fetch_one_on(conn, "SELECT enabled FROM proto_rip ORDER BY id LIMIT 1")
    return bool(row["enabled"]) if row is not None else False


def clear_rip_routes(conn: db.Connection) -> None:
    """Clear structured RIP route snapshots when RIP is disabled."""
    for table_name in RIP_ROUTE_TABLES:
        db.execute_on(conn, f"DELETE FROM {table_name}")


def replace_rip_routes(conn: db.Connection, table_name: str, command_id: int, rows: list[BirdRouteRow]) -> None:
    """Replace the current structured RIP route snapshot for one command run."""
    if table_name not in RIP_ROUTE_TABLES:
        raise ValueError(f"Unsupported RIP route table: {table_name}")
    db.execute_on(conn, f"DELETE FROM {table_name}")
    db.executemany_on(conn, f"""
        INSERT INTO {table_name} (
            command_id, table_name, route_prefix, route_type, source_protocol, since, selected,
            metric, next_hop, iface_name, raw_route, raw_detail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", [
        (command_id, row.table_name, row.route_prefix, row.route_type, row.source_protocol,
         row.since, 1 if row.selected else 0, row.metric, row.next_hop, row.iface_name,
         row.raw_route, row.raw_detail)
        for row in rows
    ])


def prune_old_command_runs(conn: db.Connection, command_text: str) -> None:
    """Keep diagnostic command history bounded per command."""
    db.execute_on(conn, """
        DELETE FROM diagnostic_command_run WHERE command = ? AND id NOT IN (
            SELECT id FROM diagnostic_command_run WHERE command = ?
            ORDER BY collected_at DESC, id DESC LIMIT ?
        )""", (command_text, command_text, COLLECTORD_BIRD_COMMAND_RETENTION))
