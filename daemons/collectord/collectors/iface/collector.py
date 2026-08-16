"""Network interface state collector."""

from __future__ import annotations

from core import db
from core.constants import COLLECTORD_IFACE_INTERVAL_SECONDS, IFACE_DB_PATH
from core.process import command_exists

from .parser import parse_ifconfig
from .repository import replace_addresses, upsert_interface, upsert_proc_values, upsert_stats


class IfaceCollector:
    """Collect network interface inventory and counters into iface.db."""

    name = "interfaces"
    interval_seconds = COLLECTORD_IFACE_INTERVAL_SECONDS

    def is_available(self) -> bool:
        """Return whether the operating-system interface command is available."""
        return command_exists("ifconfig")

    def collect(self) -> None:
        """Collect one snapshot of interface data into SQLite."""
        interfaces = parse_ifconfig()
        with db.transaction(IFACE_DB_PATH) as conn:
            for iface in interfaces:
                iface_id = upsert_interface(conn, iface)
                replace_addresses(conn, iface_id, iface)
                upsert_stats(conn, iface_id, iface.stats)
                upsert_proc_values(conn, iface_id, iface.name)
