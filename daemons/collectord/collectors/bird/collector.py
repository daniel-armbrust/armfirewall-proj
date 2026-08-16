"""BIRD protocol diagnostics collector."""

from __future__ import annotations

from core import db
from core.constants import (
    BIRD_DB_PATH,
    COLLECTORD_BIRD_PROTOCOLS_INTERVAL_SECONDS,
    COLLECTORD_BIRD_RIP_DIAGNOSTIC_COMMANDS,
    COLLECTORD_BIRD_SHOW_PROTOCOLS_COMMAND,
)

from .client import bird_is_available, run_bird_command
from .models import BirdProtocolRow
from .parser import parse_show_protocols, parse_show_routes
from .repository import (
    clear_rip_routes,
    ensure_rip_route_tables,
    insert_command_run,
    insert_protocol_rows,
    prune_old_command_runs,
    replace_rip_routes,
    rip_protocol_enabled,
)


class BirdProtocolsCollector:
    """Collect and persist BIRD protocol status snapshots."""

    name = "bird-protocols"
    interval_seconds = COLLECTORD_BIRD_PROTOCOLS_INTERVAL_SECONDS

    def is_available(self) -> bool:
        """Return whether the BIRD service and diagnostic client are available."""
        return bird_is_available()

    def collect(self) -> None:
        """Run BIRD diagnostic commands and store raw plus parsed output."""
        completed, duration_ms = run_bird_command(COLLECTORD_BIRD_SHOW_PROTOCOLS_COMMAND)
        command_text = " ".join(COLLECTORD_BIRD_SHOW_PROTOCOLS_COMMAND)
        rows = parse_show_protocols(completed.stdout) if completed.returncode == 0 else []

        with db.transaction(BIRD_DB_PATH) as conn:
            command_id = insert_command_run(conn, command_text, completed, duration_ms)
            insert_protocol_rows(conn, command_id, rows)
            prune_old_command_runs(conn, command_text)

            ensure_rip_route_tables(conn)
            rip_protocol_name = runtime_rip_protocol_name(rows)
            if not rip_protocol_enabled(conn) or not rip_protocol_name:
                clear_rip_routes(conn)
                return

            for key, command in COLLECTORD_BIRD_RIP_DIAGNOSTIC_COMMANDS:
                resolved_command = [rip_protocol_name if part == "rip1" else part for part in command]
                completed, duration_ms = run_bird_command(resolved_command)
                command_text = " ".join(resolved_command)
                command_id = insert_command_run(conn, command_text, completed, duration_ms)
                if completed.returncode == 0 and key in {"learned-routes", "exported-routes"}:
                    table_name = "rip_imported_routes" if key == "learned-routes" else "rip_exported_routes"
                    replace_rip_routes(conn, table_name, command_id, parse_show_routes(completed.stdout))
                prune_old_command_runs(conn, command_text)


def runtime_rip_protocol_name(rows: list[BirdProtocolRow]) -> str | None:
    """Return the active BIRD RIP protocol name from show protocols output."""
    for row in rows:
        if row.proto.lower() == "rip":
            return row.name
    return None
