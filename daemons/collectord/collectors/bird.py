"""BIRD diagnostic collectors for armfirewall-collectord."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from core import db
from core.process import run_command

from ..constants import (
    BIRD_COMMAND_RETENTION,
    BIRD_COMMAND_TIMEOUT_SECONDS,
    BIRD_DB_PATH,
    BIRD_PROTOCOLS_INTERVAL_SECONDS,
    BIRD_RIP_DIAGNOSTIC_COMMANDS,
    BIRD_SHOW_PROTOCOLS_COMMAND,
)


@dataclass(frozen=True)
class BirdProtocolRow:
    """One parsed row from birdcl show protocols."""

    name: str
    proto: str
    table_name: str | None
    state: str
    since: str | None
    info: str | None
    raw_line: str


@dataclass(frozen=True)
class BirdRouteRow:
    """One parsed row from birdcl show route output."""

    table_name: str | None
    route_prefix: str
    route_type: str | None
    source_protocol: str | None
    since: str | None
    selected: bool
    metric: int | None
    next_hop: str | None
    iface_name: str | None
    raw_route: str
    raw_detail: str | None


class BirdProtocolsCollector:
    """Collect and persist BIRD protocol status snapshots."""

    name = "bird-protocols"
    interval_seconds = BIRD_PROTOCOLS_INTERVAL_SECONDS

    def collect(self) -> None:
        """Run BIRD diagnostic commands and store raw plus parsed output."""
        completed, duration_ms = run_bird_command(BIRD_SHOW_PROTOCOLS_COMMAND)
        command_text = " ".join(BIRD_SHOW_PROTOCOLS_COMMAND)
        rows = parse_show_protocols(completed.stdout) if completed.returncode == 0 else []

        with db.transaction(BIRD_DB_PATH) as conn:
            command_id = insert_command_run(conn, command_text, completed, duration_ms)

            db.executemany_on(
                conn,
                """
                INSERT INTO diagnostic_protocol (
                    command_id, name, proto, table_name, state, since, info, raw_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        command_id,
                        row.name,
                        row.proto,
                        row.table_name,
                        row.state,
                        row.since,
                        row.info,
                        row.raw_line,
                    )
                    for row in rows
                ],
            )
            prune_old_command_runs(conn, command_text)

            ensure_rip_route_tables(conn)
            rip_protocol_name = runtime_rip_protocol_name(rows)
            if not rip_protocol_enabled(conn) or not rip_protocol_name:
                clear_rip_routes(conn)
                return
            for key, command in BIRD_RIP_DIAGNOSTIC_COMMANDS:
                resolved_command = [rip_protocol_name if part == "rip1" else part for part in command]
                completed, duration_ms = run_bird_command(resolved_command)
                command_text = " ".join(resolved_command)
                command_id = insert_command_run(conn, command_text, completed, duration_ms)
                if completed.returncode == 0 and key in {"learned-routes", "exported-routes"}:
                    table_name = "rip_imported_routes" if key == "learned-routes" else "rip_exported_routes"
                    rows = parse_show_routes(completed.stdout)
                    replace_rip_routes(conn, table_name, command_id, rows)
                prune_old_command_runs(conn, command_text)


def runtime_rip_protocol_name(rows: list[BirdProtocolRow]) -> str | None:
    """Return the active BIRD RIP protocol name from show protocols output."""
    for row in rows:
        if row.proto.lower() == "rip":
            return row.name
    return None


def run_bird_command(command: list[str]):
    """Run one birdcl command and return the result plus duration."""
    started = time.monotonic()
    completed = run_command(
        command,
        check=False,
        timeout=BIRD_COMMAND_TIMEOUT_SECONDS,
    )
    return completed, int((time.monotonic() - started) * 1000)


def insert_command_run(conn: db.Connection, command_text: str, completed, duration_ms: int) -> int:
    """Persist one diagnostic command execution."""
    cursor = db.execute_on(
        conn,
        """
        INSERT INTO diagnostic_command_run (
            command, exit_code, stdout, stderr, duration_ms
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (command_text, completed.returncode, completed.stdout, completed.stderr, duration_ms),
    )
    return int(cursor.lastrowid)


def parse_show_protocols(output: str) -> list[BirdProtocolRow]:
    """Parse birdcl show protocols tabular output."""
    rows: list[BirdProtocolRow] = []
    header_seen = False

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("BIRD "):
            continue
        if stripped.startswith("Name") and "Proto" in stripped and "State" in stripped:
            header_seen = True
            continue
        if not header_seen:
            continue

        parts = stripped.split(None, 5)
        if len(parts) < 5:
            continue

        name, proto, table_name, state, since = parts[:5]
        info = parts[5].strip() if len(parts) > 5 and parts[5].strip() else None
        rows.append(
            BirdProtocolRow(
                name=name,
                proto=proto,
                table_name=None if table_name == "---" else table_name,
                state=state,
                since=since,
                info=info,
                raw_line=line,
            )
        )

    return rows


ROUTE_LINE_RE = re.compile(
    r"^(?P<prefix>\S+)\s+(?P<rtype>\S+)\s+\[(?P<source>\S+)\s+(?P<since>[^\]]+)\]\s+"
    r"(?P<selected>\*)?\s*(?:\((?P<metric>\d+)\))?"
)


def parse_show_routes(output: str) -> list[BirdRouteRow]:
    """Parse birdcl show route output into structured route rows."""
    rows: list[BirdRouteRow] = []
    pending: BirdRouteRow | None = None
    current_table: str | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending is not None:
            rows.append(pending)
            pending = None

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("BIRD "):
            continue
        if stripped.startswith("Table "):
            flush_pending()
            current_table = stripped.removeprefix("Table ").rstrip(":") or None
            continue

        match = ROUTE_LINE_RE.match(stripped)
        if match:
            flush_pending()
            metric_text = match.group("metric")
            pending = BirdRouteRow(
                table_name=current_table,
                route_prefix=match.group("prefix"),
                route_type=match.group("rtype"),
                source_protocol=match.group("source"),
                since=match.group("since"),
                selected=bool(match.group("selected")),
                metric=int(metric_text) if metric_text is not None else None,
                next_hop=None,
                iface_name=None,
                raw_route=line,
                raw_detail=None,
            )
            continue

        if pending is None:
            continue

        next_hop = pending.next_hop
        iface_name = pending.iface_name
        via_match = re.search(r"\bvia\s+(\S+)\s+on\s+(\S+)", stripped)
        dev_match = re.search(r"\bdev\s+(\S+)", stripped)
        if via_match:
            next_hop = via_match.group(1)
            iface_name = via_match.group(2)
        elif dev_match:
            iface_name = dev_match.group(1)

        pending = BirdRouteRow(
            table_name=pending.table_name,
            route_prefix=pending.route_prefix,
            route_type=pending.route_type,
            source_protocol=pending.source_protocol,
            since=pending.since,
            selected=pending.selected,
            metric=pending.metric,
            next_hop=next_hop,
            iface_name=iface_name,
            raw_route=pending.raw_route,
            raw_detail=stripped,
        )

    flush_pending()
    return rows


def ensure_rip_route_tables(conn: db.Connection) -> None:
    """Create structured RIP route tables for upgraded installations."""
    for table_name in ("rip_imported_routes", "rip_exported_routes"):
        db.execute_on(
            conn,
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 command_id INTEGER NOT NULL,
                 table_name TEXT,
                 route_prefix TEXT NOT NULL,
                 route_type TEXT,
                 source_protocol TEXT,
                 since TEXT,
                 selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
                 metric INTEGER,
                 next_hop TEXT,
                 iface_name TEXT,
                 raw_route TEXT NOT NULL,
                 raw_detail TEXT,
                 collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                 FOREIGN KEY (command_id) REFERENCES diagnostic_command_run(id) ON DELETE CASCADE
            )
            """,
        )
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
    for table_name in ("rip_imported_routes", "rip_exported_routes"):
        db.execute_on(conn, f"DELETE FROM {table_name}")


def replace_rip_routes(conn: db.Connection, table_name: str, command_id: int, rows: list[BirdRouteRow]) -> None:
    """Replace the current structured RIP route snapshot for one command run."""
    if table_name not in {"rip_imported_routes", "rip_exported_routes"}:
        raise ValueError(f"Unsupported RIP route table: {table_name}")

    db.execute_on(conn, f"DELETE FROM {table_name}")
    db.executemany_on(
        conn,
        f"""
        INSERT INTO {table_name} (
            command_id, table_name, route_prefix, route_type, source_protocol, since, selected,
            metric, next_hop, iface_name, raw_route, raw_detail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                command_id,
                row.table_name,
                row.route_prefix,
                row.route_type,
                row.source_protocol,
                row.since,
                1 if row.selected else 0,
                row.metric,
                row.next_hop,
                row.iface_name,
                row.raw_route,
                row.raw_detail,
            )
            for row in rows
        ],
    )


def prune_old_command_runs(conn: db.Connection, command_text: str) -> None:
    """Keep diagnostic command history bounded per command."""
    db.execute_on(
        conn,
        """
        DELETE FROM diagnostic_command_run
        WHERE command = ?
          AND id NOT IN (
              SELECT id
              FROM diagnostic_command_run
              WHERE command = ?
              ORDER BY collected_at DESC, id DESC
              LIMIT ?
          )
        """,
        (command_text, command_text, BIRD_COMMAND_RETENTION),
    )
