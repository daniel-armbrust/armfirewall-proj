"""Service catalog helpers used by the service management daemon."""

from __future__ import annotations

from typing import Any

from core import db
from core.constants import SERVICES_DB_PATH


SERVICE_RUNTIME_COLUMNS = {
    "runtime_installed": "INTEGER NOT NULL DEFAULT 0 CHECK(runtime_installed IN (0, 1))",
    "runtime_state": "TEXT NOT NULL DEFAULT 'NOT INSTALLED'",
    "runtime_pid": "TEXT NOT NULL DEFAULT '-'",
    "runtime_uptime": "TEXT NOT NULL DEFAULT '-'",
    "runtime_details": "TEXT NOT NULL DEFAULT 'Not synchronized yet'",
    "runtime_updated_at": "TEXT",
    "autostart_enabled": "INTEGER NOT NULL DEFAULT 1 CHECK(autostart_enabled IN (0, 1))",
}


def ensure_service_runtime_columns() -> None:
    """Ensure services.db has runtime status columns."""
    with db.transaction(SERVICES_DB_PATH) as conn:
        rows = db.fetch_all_on(conn, "PRAGMA table_info(services)")
        existing = {str(row["name"]) for row in rows}

        for column_name, column_definition in SERVICE_RUNTIME_COLUMNS.items():
            if column_name not in existing:
                db.execute_on(conn, f"ALTER TABLE services ADD COLUMN {column_name} {column_definition}")


def service_exists(name: str) -> bool:
    """Return whether an enabled service exists in the daemon catalog."""
    row = db.fetch_one(
        """
        SELECT 1
        FROM services
        WHERE name = ?
          AND enabled = 1
        """,
        (name,),
        db_path=SERVICES_DB_PATH,
    )
    return row is not None


def set_service_autostart_enabled(name: str, enabled: bool) -> None:
    """Persist whether a managed service should start with supervisord."""
    ensure_service_runtime_columns()
    with db.transaction(SERVICES_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            "UPDATE services SET autostart_enabled = ? WHERE name = ?",
            (1 if enabled else 0, name),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Managed service was not found: {name}")


def optional_service_for_daemon(name: str) -> dict[str, Any] | None:
    """Return full optional service metadata for daemon execution."""
    return db.fetch_one(
        """
        SELECT
            name,
            package_name AS package,
            binary_path AS binary,
            supervisor_program
        FROM services
        WHERE name = ?
          AND service_group = 'optional'
          AND enabled = 1
        """,
        (name,),
        db_path=SERVICES_DB_PATH,
    )


def persist_supervisor_statuses(rows: list[dict[str, str]]) -> None:
    """Persist current supervisord runtime status into services.db."""
    ensure_service_runtime_columns()
    by_name = {str(row.get("name") or ""): row for row in rows}

    with db.transaction(SERVICES_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            UPDATE services
               SET runtime_installed = 0,
                   runtime_state = 'NOT INSTALLED',
                   runtime_pid = '-',
                   runtime_uptime = '-',
                   runtime_details = 'Missing from supervisord.conf',
                   runtime_updated_at = CURRENT_TIMESTAMP
             WHERE enabled = 1
            """,
        )

        for service_name, row in by_name.items():
            db.execute_on(
                conn,
                """
                UPDATE services
                   SET runtime_installed = 1,
                       runtime_state = ?,
                       runtime_pid = ?,
                       runtime_uptime = ?,
                       runtime_details = ?,
                       runtime_updated_at = CURRENT_TIMESTAMP
                 WHERE name = ?
                   AND enabled = 1
                """,
                (
                    str(row.get("state") or "UNKNOWN"),
                    str(row.get("pid") or "-"),
                    str(row.get("uptime") or "-"),
                    str(row.get("details") or "-"),
                    service_name,
                ),
            )
