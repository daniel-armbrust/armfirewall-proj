from __future__ import annotations

from web.services.api import service_installed


def squid_service_installed() -> bool:
    """Return whether the Squid proxy service is installed."""
    return service_installed("squid")
