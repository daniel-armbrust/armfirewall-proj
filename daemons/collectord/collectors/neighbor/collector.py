"""Kernel neighbor-cache collector."""
from __future__ import annotations

import subprocess

from core import db
from core.constants import NETWORK_DB_PATH
from core.process import command_exists


class NeighborCollector:
    """Collect iproute2 neighbor entries into network.db."""
    name = "neighbors"
    interval_seconds = 5

    def is_available(self) -> bool:
        return command_exists("ip")

    def collect(self) -> None:
        result = subprocess.run(["ip", "neighbor", "show"], check=False, capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "ip neighbor show failed")
        entries = [self._parse(line) for line in result.stdout.splitlines()]
        entries = [entry for entry in entries if entry]
        with db.transaction(NETWORK_DB_PATH) as conn:
            db.execute_on(conn, """INSERT INTO neighbor_snapshot (id, source, collected_at)
                VALUES (1, 'ip-neighbor', CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET source=excluded.source, collected_at=CURRENT_TIMESTAMP""")
            db.execute_on(conn, "DELETE FROM neighbor_entry WHERE snapshot_id = 1")
            db.executemany_on(conn, """INSERT INTO neighbor_entry
                (snapshot_id, addr_family, ip_address, mac_address, iface_name, state, flags, raw_entry, collected_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""", entries)

    @staticmethod
    def _parse(line: str) -> tuple[str, str, str, str, str, str, str] | None:
        parts = line.split()
        if not parts:
            return None
        address, iface, mac, state, flags = parts[0], "-", "-", "UNKNOWN", []
        index = 1
        states = {"INCOMPLETE", "REACHABLE", "STALE", "DELAY", "PROBE", "FAILED", "NOARP", "PERMANENT"}
        while index < len(parts):
            token = parts[index]; next_value = parts[index + 1] if index + 1 < len(parts) else ""
            if token == "dev" and next_value: iface = next_value; index += 2; continue
            if token == "lladdr" and next_value: mac = next_value; index += 2; continue
            if token.upper() in states: state = token.upper()
            index += 1
        return ("ipv6" if ":" in address else "ipv4", address, mac, iface, state, ", ".join(flags) or "-", line)
