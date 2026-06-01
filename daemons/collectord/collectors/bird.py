"""BIRD diagnostic collectors for armfirewall-collectord."""

from __future__ import annotations

import time
from dataclasses import dataclass

from core import db
from core.process import run_command

from ..constants import (
    BIRD_COMMAND_RETENTION,
    BIRD_COMMAND_TIMEOUT_SECONDS,
    BIRD_DB_PATH,
    BIRD_PROTOCOLS_INTERVAL_SECONDS,
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


class BirdProtocolsCollector:
    """Collect and persist BIRD protocol status snapshots."""

    name = "bird-protocols"
    interval_seconds = BIRD_PROTOCOLS_INTERVAL_SECONDS

    def collect(self) -> None:
        """Run birdcl show protocols and store raw plus parsed output."""
        started = time.monotonic()
        completed = run_command(
            BIRD_SHOW_PROTOCOLS_COMMAND,
            check=False,
            timeout=BIRD_COMMAND_TIMEOUT_SECONDS,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        command_text = " ".join(BIRD_SHOW_PROTOCOLS_COMMAND)
        rows = parse_show_protocols(completed.stdout) if completed.returncode == 0 else []

        with db.transaction(BIRD_DB_PATH) as conn:
            cursor = db.execute_on(
                conn,
                """
                INSERT INTO diagnostic_command_run (
                    command, exit_code, stdout, stderr, duration_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (command_text, completed.returncode, completed.stdout, completed.stderr, duration_ms),
            )
            command_id = int(cursor.lastrowid)

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
