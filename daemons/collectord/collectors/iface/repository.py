"""SQLite persistence for network interface snapshots."""

from __future__ import annotations

from pathlib import Path

from core import db
from core.constants import COLLECTORD_IFACE_PROC_ITEMS

from .models import InterfaceInfo, InterfaceStats


def existing_metadata(conn: db.Connection, name: str) -> dict[str, object]:
    """Return persisted role metadata for one interface."""
    row = db.fetch_one_on(conn, "SELECT role, description, protected FROM ifaces WHERE name = ?", (name,))
    return dict(row) if row else {"role": "UNKNOWN", "description": "", "protected": 0}


def description_for(name: str, role: str) -> str:
    """Build a default human-readable interface description."""
    if role in {"LAN", "WAN"}:
        return f"{role} interface persisted in iface.db: {name}"
    return f"Network interface discovered by ifconfig -a: {name}"


def upsert_interface(conn: db.Connection, iface: InterfaceInfo) -> int:
    """Insert or update the main interface row."""
    metadata = existing_metadata(conn, iface.name)
    role = str(metadata["role"] or "UNKNOWN")
    description = str(metadata["description"] or description_for(iface.name, role))
    protected = int(metadata["protected"] or 0)
    db.execute_on(conn, """
        INSERT INTO ifaces (name, is_actived, description, mtu, mac_address, role, type, speed_mbps, duplex, protected, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(name) DO UPDATE SET is_actived=excluded.is_actived, description=excluded.description,
            mtu=excluded.mtu, mac_address=excluded.mac_address, type=excluded.type,
            speed_mbps=excluded.speed_mbps, duplex=excluded.duplex, collected_at=CURRENT_TIMESTAMP
        """, (iface.name, 1 if "UP" in iface.flags else 0, description, iface.mtu, iface.mac_address,
              role, iface.type, iface.speed_mbps, iface.duplex, protected))
    row = db.fetch_one_on(conn, "SELECT id FROM ifaces WHERE name = ?", (iface.name,))
    if row is None:
        raise RuntimeError(f"Could not locate iface row for {iface.name}")
    return int(row[0])


def replace_addresses(conn: db.Connection, iface_id: int, iface: InterfaceInfo) -> None:
    """Replace all stored addresses for an interface."""
    db.execute_on(conn, "DELETE FROM addresses WHERE iface_id = ?", (iface_id,))
    db.executemany_on(conn, """
        INSERT INTO addresses (iface_id, addr_family, addr, prefixlen, broadcast, scopeid, is_secondary, iface_name_secondary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", [
        (iface_id, item.addr_family, item.addr, item.prefixlen, item.broadcast, item.scopeid,
         item.is_secondary, item.iface_name_secondary) for item in iface.addresses
    ])


def upsert_stats(conn: db.Connection, iface_id: int, stats: InterfaceStats) -> None:
    """Insert or update current traffic statistics."""
    db.execute_on(conn, """
        INSERT INTO stats (iface_id, rx_bytes, rx_packets, rx_errors, rx_dropped, rx_fifo, rx_frame, rx_multicast,
            tx_bytes, tx_packets, tx_errors, tx_dropped, tx_fifo, tx_collisions, tx_carrier, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(iface_id) DO UPDATE SET rx_bytes=excluded.rx_bytes, rx_packets=excluded.rx_packets,
            rx_errors=excluded.rx_errors, rx_dropped=excluded.rx_dropped, rx_fifo=excluded.rx_fifo,
            rx_frame=excluded.rx_frame, rx_multicast=excluded.rx_multicast, tx_bytes=excluded.tx_bytes,
            tx_packets=excluded.tx_packets, tx_errors=excluded.tx_errors, tx_dropped=excluded.tx_dropped,
            tx_fifo=excluded.tx_fifo, tx_collisions=excluded.tx_collisions, tx_carrier=excluded.tx_carrier,
            collected_at=CURRENT_TIMESTAMP
        """, (iface_id, stats.rx_bytes, stats.rx_packets, stats.rx_errors, stats.rx_dropped, stats.rx_fifo,
              stats.rx_frame, stats.rx_multicast, stats.tx_bytes, stats.tx_packets, stats.tx_errors,
              stats.tx_dropped, stats.tx_fifo, stats.tx_collisions, stats.tx_carrier))


def upsert_proc_values(conn: db.Connection, iface_id: int, iface_name: str) -> None:
    """Insert or update collected proc settings for an interface."""
    for family, proc_key, description in COLLECTORD_IFACE_PROC_ITEMS:
        proc_path = Path("/proc/sys/net") / family / "conf" / iface_name / proc_key
        try:
            value = proc_path.read_text().strip()
        except OSError:
            continue
        db.execute_on(conn, """
            INSERT INTO proc (iface_id, addr_family, proc_path, description, default_value, desired_value, collected_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(iface_id, addr_family, proc_path) DO UPDATE SET description=excluded.description,
                default_value=excluded.default_value, desired_value=COALESCE(proc.desired_value, excluded.desired_value),
                collected_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            """, (iface_id, family, str(proc_path), description, value, value))
