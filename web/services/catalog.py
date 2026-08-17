"""Service catalog helpers used by the Services web module."""

from __future__ import annotations

from typing import Any

from core import db
from core.constants import SERVICES_DB_PATH, SUPERVISOR_CONF


PUBLIC_SERVICE_COLUMNS = """
    name,
    display_name,
    kind,
    description,
    service_group,
    protected,
    restart_allowed,
    package_name,
    enabled
"""


RUNTIME_SERVICE_COLUMNS = """
    runtime_installed,
    runtime_state,
    runtime_pid,
    runtime_uptime,
    runtime_details,
    runtime_updated_at,
    autostart_enabled
"""


def ensure_service_control_columns() -> None:
    """Ensure the persisted Supervisor enablement state is available."""
    with db.transaction(SERVICES_DB_PATH) as conn:
        columns = {str(row["name"]) for row in db.fetch_all_on(conn, "PRAGMA table_info(services)")}
        if "autostart_enabled" not in columns:
            db.execute_on(
                conn,
                "ALTER TABLE services ADD COLUMN autostart_enabled INTEGER NOT NULL DEFAULT 1 CHECK(autostart_enabled IN (0, 1))",
            )
            for service_name, enabled in configured_supervisor_autostarts().items():
                db.execute_on(
                    conn,
                    "UPDATE services SET autostart_enabled = ? WHERE name = ?",
                    (1 if enabled else 0, service_name),
                )

        db.execute_on(
            conn,
            "UPDATE services SET restart_allowed = 1 WHERE name = 'armfirewall-collectord'",
        )


def configured_supervisor_autostarts() -> dict[str, bool]:
    """Read managed program autostart values from supervisord.conf."""
    if not SUPERVISOR_CONF.exists():
        return {}

    values: dict[str, bool] = {}
    service_name: str | None = None
    for raw_line in SUPERVISOR_CONF.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[program:") and line.endswith("]"):
            service_name = line[len("[program:"):-1]
        elif line.startswith("["):
            service_name = None
        elif service_name and line.startswith("autostart="):
            values[service_name] = line.partition("=")[2].strip().lower() == "true"
    return values


def services_table_columns() -> set[str]:
    """Return the current services table columns."""
    ensure_service_control_columns()
    with db.connection(SERVICES_DB_PATH) as conn:
        return {str(row["name"]) for row in db.fetch_all_on(conn, "PRAGMA table_info(services)")}


def service_runtime_columns_available() -> bool:
    """Return whether services.db has persisted runtime status columns."""
    columns = services_table_columns()
    return {
        "runtime_installed",
        "runtime_state",
        "runtime_pid",
        "runtime_uptime",
        "runtime_details",
        "runtime_updated_at",
        "autostart_enabled",
    }.issubset(columns)


def service_public_catalog(service_group: str, *, include_disabled: bool = False) -> list[dict[str, Any]]:
    """Return enabled service metadata that the web layer may display."""
    runtime_available = service_runtime_columns_available()
    selected_columns = f"{PUBLIC_SERVICE_COLUMNS}, {RUNTIME_SERVICE_COLUMNS}" if runtime_available else PUBLIC_SERVICE_COLUMNS
    enabled_filter = "" if include_disabled else "AND enabled = 1"
    rows = db.fetch_all(
        f"""
        SELECT {selected_columns}
        FROM services
        WHERE service_group = ?
          {enabled_filter}
        ORDER BY sort_order, name
        """,
        (service_group,),
        db_path=SERVICES_DB_PATH,
    )

    if runtime_available:
        return rows

    for row in rows:
        row.update(
            {
                "runtime_installed": 0,
                "runtime_state": "NOT INSTALLED",
                "runtime_pid": "-",
                "runtime_uptime": "-",
                "runtime_details": "Runtime status has not been synchronized.",
                "runtime_updated_at": None,
            }
        )

    return rows


def service_by_name(name: str) -> dict[str, Any] | None:
    """Return one enabled service visible to the web layer."""
    row = db.fetch_one(
        """
        SELECT name, service_group
        FROM services
        WHERE name = ?
        """,
        (name,),
        db_path=SERVICES_DB_PATH,
    )
    if row is None:
        return None

    services = service_public_catalog(str(row["service_group"]), include_disabled=True)
    return next((item for item in services if item["name"] == name), None)


def main_service_public_catalog() -> list[dict[str, Any]]:
    """Return enabled main service metadata for GUI status pages."""
    return service_public_catalog("main", include_disabled=True)


def optional_service_public_catalog() -> list[dict[str, Any]]:
    """Return optional service metadata that the web layer may display."""
    return service_public_catalog("optional")
