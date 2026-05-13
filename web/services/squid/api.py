from __future__ import annotations

from web.services.api import supervisor_program_exists


def squid_service_installed() -> bool:
    """Return whether the Squid proxy service is registered in supervisord."""
    return supervisor_program_exists("squid")
