"""Shared template context helpers for the ArmFirewall Web layer."""

from __future__ import annotations

from typing import Any

from core import db
from web.services.api import service_installed


def menu_context() -> dict[str, Any]:
    """Return dynamic menu state for template rendering."""
    try:
        squid_installed = service_installed("squid")
    except (FileNotFoundError, db.DatabaseError):
        squid_installed = False

    try:
        libreswan_installed = service_installed("libreswan")
    except (FileNotFoundError, db.DatabaseError):
        libreswan_installed = False

    return {
        "squid_installed": squid_installed,
        "libreswan_installed": libreswan_installed,
    }
