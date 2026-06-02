from __future__ import annotations

from web.services.routingprotocols.birdsettings.api import (
    get_bird_diagnostics,
    get_global_settings,
    read_bird_logs,
    render_global_config,
    save_global_settings,
    settings_from_db,
)
from web.services.routingprotocols.common import bird_service_installed
from web.services.routingprotocols.rip.api import (
    get_rip_diagnostics,
    get_rip_settings,
    rip_settings_from_db,
    save_rip_settings,
)

__all__ = [
    "bird_service_installed",
    "get_bird_diagnostics",
    "get_global_settings",
    "get_rip_diagnostics",
    "get_rip_settings",
    "read_bird_logs",
    "render_global_config",
    "rip_settings_from_db",
    "save_global_settings",
    "save_rip_settings",
    "settings_from_db",
]
