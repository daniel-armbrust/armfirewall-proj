"""Network interface inventory used by DNSMasq."""

from __future__ import annotations

from typing import Any

from core import db
from core import iface as iface_module


def list_interfaces() -> list[dict[str, Any]]:
    """Return interfaces available for DNSMasq binding and validation."""
    try:
        return iface_module.get_interfaces().get("interfaces", [])
    except (FileNotFoundError, db.DatabaseError):
        return []
