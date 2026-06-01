"""Service catalog helpers used by the Services web module."""

from __future__ import annotations

from typing import Any

from core import db
from core.constants import SERVICES_DB_PATH


PUBLIC_SERVICE_COLUMNS = """
    name,
    display_name,
    kind,
    description,
    service_group,
    protected,
    restart_allowed,
    package_name
"""


RUNTIME_SERVICE_COLUMNS = """
    runtime_installed,
    runtime_state,
    runtime_pid,
    runtime_uptime,
    runtime_details,
    runtime_updated_at
"""


def services_table_columns() -> set[str]:
    """Return the current services table columns."""
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
    }.issubset(columns)


def service_public_catalog(service_group: str) -> list[dict[str, Any]]:
    """Return enabled service metadata that the web layer may display."""
    runtime_available = service_runtime_columns_available()
    selected_columns = f"{PUBLIC_SERVICE_COLUMNS}, {RUNTIME_SERVICE_COLUMNS}" if runtime_available else PUBLIC_SERVICE_COLUMNS
    rows = db.fetch_all(
        f"""
        SELECT {selected_columns}
        FROM services
        WHERE service_group = ?
          AND enabled = 1
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
          AND enabled = 1
        """,
        (name,),
        db_path=SERVICES_DB_PATH,
    )
    if row is None:
        return None

    services = service_public_catalog(str(row["service_group"]))
    return next((item for item in services if item["name"] == name), None)


def main_service_public_catalog() -> list[dict[str, Any]]:
    """Return enabled main service metadata for GUI status pages."""
    return service_public_catalog("main")


def optional_service_public_catalog() -> list[dict[str, Any]]:
    """Return optional service metadata that the web layer may display."""
    return service_public_catalog("optional")
