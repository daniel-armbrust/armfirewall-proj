from __future__ import annotations

from web.services.api import service_installed


def bird_service_installed() -> bool:
    """Return whether the BIRD routing daemon is installed."""
    return service_installed("bird")
