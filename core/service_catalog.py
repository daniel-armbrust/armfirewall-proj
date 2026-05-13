"""Shared service catalog access backed by services.db."""

from __future__ import annotations

from typing import Any

from core import db
from core.constants import SERVICES_DB_PATH


PUBLIC_SERVICE_COLUMNS = """
    name,
    display_name,
    kind,
    description,
    protected,
    restart_allowed
"""


def service_public_catalog(service_group: str) -> list[dict[str, Any]]:
    """Return enabled service metadata that the web layer may display."""
    return db.fetch_all(
        f"""
        SELECT {PUBLIC_SERVICE_COLUMNS}
        FROM services
        WHERE service_group = ?
          AND enabled = 1
        ORDER BY sort_order, name
        """,
        (service_group,),
        db_path=SERVICES_DB_PATH,
    )


def main_service_public_catalog() -> list[dict[str, Any]]:
    """Return enabled main service metadata for GUI status pages."""
    return service_public_catalog("main")


def optional_service_names() -> set[str]:
    """Return supported optional service names."""
    rows = db.fetch_all(
        """
        SELECT name
        FROM services
        WHERE service_group = 'optional'
          AND enabled = 1
        """,
        db_path=SERVICES_DB_PATH,
    )
    return {str(row["name"]) for row in rows}


def optional_service_public_catalog() -> list[dict[str, Any]]:
    """Return optional service metadata that the web layer may display."""
    return service_public_catalog("optional")


def service_exists(name: str) -> bool:
    """Return whether an enabled service exists in the catalog."""
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
