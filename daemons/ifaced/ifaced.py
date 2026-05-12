#!/usr/bin/env python3
"""Persistent daemon that collects network interface data into iface.db."""

from __future__ import annotations

import ipaddress
import re
import subprocess
import time
from pathlib import Path

from core import db
from core import log as logger
from core.constants import DB_DIR
from core.process import run_command_stdout

from .constants import COLLECT_INTERVAL_SECONDS, IFACE_DB_PATH, LOG_SOURCE, PROC_ITEMS
from .models import InterfaceAddress, InterfaceInfo, InterfaceStats


def netmask_to_prefixlen(netmask: str) -> str:
    """Convert an IPv4 netmask to a prefix length."""
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen)
    except ValueError:
        return ""


def parse_ifconfig() -> list[InterfaceInfo]:
    """Parse ifconfig output into interface objects."""
    output = run_command_stdout(["ifconfig", "-a"])
    interfaces: list[InterfaceInfo] = []

    for block in re.split(r"\n\s*\n", output.strip()):
        lines = block.splitlines()
        if not lines:
            continue

        header = lines[0]
        match = re.match(r"^([^:\s]+):\s+flags=\d+<([^>]*)>\s+mtu\s+(\d+)", header)

        if not match:
            continue

        iface = InterfaceInfo(
            name=match.group(1),
            flags={flag.strip() for flag in match.group(2).split(",") if flag.strip()},
            mtu=int(match.group(3)),
        )

        for raw_line in lines[1:]:
            line = raw_line.strip()

            if line.startswith("inet "):
                parts = line.split()
                addr = parts[1]
                netmask = parts[parts.index("netmask") + 1] if "netmask" in parts else ""
                broadcast = parts[parts.index("broadcast") + 1] if "broadcast" in parts else None

                iface.addresses.append(
                    InterfaceAddress(
                        addr_family="ipv4",
                        addr=addr,
                        prefixlen=netmask_to_prefixlen(netmask),
                        broadcast=broadcast,
                    )
                )

                continue

            if line.startswith("inet6 "):
                parts = line.split()
                addr = parts[1]
                prefixlen = parts[parts.index("prefixlen") + 1] if "prefixlen" in parts else ""
                scopeid = parts[parts.index("scopeid") + 1] if "scopeid" in parts else None

                iface.addresses.append(
                    InterfaceAddress(
                        addr_family="ipv6",
                        addr=addr,
                        prefixlen=prefixlen,
                        scopeid=scopeid,
                    )
                )

                continue

            if line.startswith("ether "):
                parts = line.split()
                iface.mac_address = parts[1]
                type_match = re.search(r"\(([^)]+)\)", line)

                if type_match:
                    iface.type = type_match.group(1)
                continue

            if line.startswith("loop "):
                iface.type = "Local Loopback"
                continue

            if line.startswith("RX packets"):
                packet_match = re.search(r"RX packets\s+(\d+)\s+bytes\s+(\d+)", line)

                if packet_match:
                    iface.stats.rx_packets = int(packet_match.group(1))
                    iface.stats.rx_bytes = int(packet_match.group(2))

                continue

            if line.startswith("RX errors"):
                fields = dict(re.findall(r"(errors|dropped|overruns|frame)\s+(\d+)", line))
                iface.stats.rx_errors = int(fields.get("errors", 0))
                iface.stats.rx_dropped = int(fields.get("dropped", 0))
                iface.stats.rx_fifo = int(fields.get("overruns", 0))
                iface.stats.rx_frame = int(fields.get("frame", 0))

                continue

            if line.startswith("TX packets"):
                packet_match = re.search(r"TX packets\s+(\d+)\s+bytes\s+(\d+)", line)

                if packet_match:
                    iface.stats.tx_packets = int(packet_match.group(1))
                    iface.stats.tx_bytes = int(packet_match.group(2))

                continue

            if line.startswith("TX errors"):
                fields = dict(re.findall(r"(errors|dropped|overruns|carrier|collisions)\s+(\d+)", line))

                iface.stats.tx_errors = int(fields.get("errors", 0))
                iface.stats.tx_dropped = int(fields.get("dropped", 0))
                iface.stats.tx_fifo = int(fields.get("overruns", 0))
                iface.stats.tx_carrier = int(fields.get("carrier", 0))
                iface.stats.tx_collisions = int(fields.get("collisions", 0))

                continue

        iface.speed_mbps, iface.duplex = read_ethtool_data(iface.name)
        interfaces.append(iface)

    return interfaces


def read_ethtool_data(iface_name: str) -> tuple[int, str]:
    """Read link speed and duplex information from ethtool."""
    try:
        output = run_command_stdout(["ethtool", iface_name])
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0, "unknown"

    speed_mbps = 0
    duplex = "unknown"

    speed_match = re.search(r"Speed:\s+(\d+)Mb/s", output)

    if speed_match:
        speed_mbps = int(speed_match.group(1))

    duplex_match = re.search(r"Duplex:\s+(\w+)", output)

    if duplex_match:
        value = duplex_match.group(1).lower()

        if value == "full":
            duplex = "full-duplex"
        elif value == "half":
            duplex = "half-duplex"

    return speed_mbps, duplex


def existing_iface_metadata(conn: db.Connection, iface_name: str) -> dict[str, object]:
    """Return role metadata already persisted for one interface."""
    row = db.fetch_one_on(
        conn,
        """
        SELECT role, description, protected
        FROM ifaces
        WHERE name = ?
        """,
        (iface_name,),
    )

    if row is None:
        return {"role": "UNKNOWN", "description": "", "protected": 0}
    
    return dict(row)


def description_for_interface(iface_name: str, role: str) -> str:
    """Build a human-readable description for an interface."""

    if role == "LAN":
        return f"LAN interface persisted in iface.db: {iface_name}"
    
    if role == "WAN":
        return f"WAN interface persisted in iface.db: {iface_name}"
    
    return f"Network interface discovered by ifconfig -a: {iface_name}"


def upsert_iface(conn: db.Connection, iface: InterfaceInfo) -> int:
    """Insert or update the main interface row."""
    metadata = existing_iface_metadata(conn, iface.name)
    role = str(metadata["role"] or "UNKNOWN")
    description = str(metadata["description"] or description_for_interface(iface.name, role))
    protected = int(metadata["protected"] or 0)

    db.execute_on(
        conn,
        """
        INSERT INTO ifaces (
            name, is_actived, description, mtu, mac_address, role, type,
            speed_mbps, duplex, protected, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(name) DO UPDATE SET
            is_actived = excluded.is_actived,
            description = excluded.description,
            mtu = excluded.mtu,
            mac_address = excluded.mac_address,
            type = excluded.type,
            speed_mbps = excluded.speed_mbps,
            duplex = excluded.duplex,
            collected_at = CURRENT_TIMESTAMP
        """,
        (
            iface.name,
            1 if "UP" in iface.flags else 0,
            description,
            iface.mtu,
            iface.mac_address,
            role,
            iface.type,
            iface.speed_mbps,
            iface.duplex,
            protected,
        ),
    )

    row = db.fetch_one_on(conn, "SELECT id FROM ifaces WHERE name = ?", (iface.name,))

    if row is None:
        raise RuntimeError(f"Could not locate iface row for {iface.name}")
    
    return int(row[0])


def replace_addresses(conn: db.Connection, iface_id: int, iface: InterfaceInfo) -> None:
    """Replace all stored addresses for an interface."""
    db.execute_on(conn, "DELETE FROM addresses WHERE iface_id = ?", (iface_id,))

    db.executemany_on(
        conn,
        """
        INSERT INTO addresses (
            iface_id, addr_family, addr, prefixlen, broadcast, scopeid,
            is_secondary, iface_name_secondary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                iface_id,
                address.addr_family,
                address.addr,
                address.prefixlen,
                address.broadcast,
                address.scopeid,
                address.is_secondary,
                address.iface_name_secondary,
            )
            for address in iface.addresses
        ],
    )


def upsert_stats(conn: db.Connection, iface_id: int, stats: InterfaceStats) -> None:
    """Insert or update current traffic statistics."""
    db.execute_on(
        conn,
        """
        INSERT INTO stats (
            iface_id,
            rx_bytes, rx_packets, rx_errors, rx_dropped, rx_fifo, rx_frame, rx_multicast,
            tx_bytes, tx_packets, tx_errors, tx_dropped, tx_fifo, tx_collisions, tx_carrier,
            collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(iface_id) DO UPDATE SET
            rx_bytes = excluded.rx_bytes,
            rx_packets = excluded.rx_packets,
            rx_errors = excluded.rx_errors,
            rx_dropped = excluded.rx_dropped,
            rx_fifo = excluded.rx_fifo,
            rx_frame = excluded.rx_frame,
            rx_multicast = excluded.rx_multicast,
            tx_bytes = excluded.tx_bytes,
            tx_packets = excluded.tx_packets,
            tx_errors = excluded.tx_errors,
            tx_dropped = excluded.tx_dropped,
            tx_fifo = excluded.tx_fifo,
            tx_collisions = excluded.tx_collisions,
            tx_carrier = excluded.tx_carrier,
            collected_at = CURRENT_TIMESTAMP
        """,
        (
            iface_id,
            stats.rx_bytes,
            stats.rx_packets,
            stats.rx_errors,
            stats.rx_dropped,
            stats.rx_fifo,
            stats.rx_frame,
            stats.rx_multicast,
            stats.tx_bytes,
            stats.tx_packets,
            stats.tx_errors,
            stats.tx_dropped,
            stats.tx_fifo,
            stats.tx_collisions,
            stats.tx_carrier,
        ),
    )


def read_proc_value(path: Path) -> str | None:
    """Read a proc file value when it exists."""
    try:
        return path.read_text().strip()
    except OSError:
        return None


def upsert_proc_values(conn: db.Connection, iface_id: int, iface_name: str) -> None:
    """Insert or update collected proc settings for an interface."""
    for family, proc_key, description in PROC_ITEMS:
        proc_path = Path("/proc/sys/net") / family / "conf" / iface_name / proc_key
        value = read_proc_value(proc_path)

        if value is None:
            continue

        db.execute_on(
            conn,
            """
            INSERT INTO proc (
                iface_id, addr_family, proc_path, description,
                default_value, desired_value, collected_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(iface_id, addr_family, proc_path) DO UPDATE SET
                description = excluded.description,
                default_value = excluded.default_value,
                desired_value = COALESCE(proc.desired_value, excluded.desired_value),
                collected_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """,
            (iface_id, family, str(proc_path), description, value, value),
        )


def collect_once(conn: db.Connection) -> None:
    """Collect one snapshot of interface data into SQLite."""
    interfaces = parse_ifconfig()

    with conn:
        for iface in interfaces:
            iface_id = upsert_iface(conn, iface)
            replace_addresses(conn, iface_id, iface)
            upsert_stats(conn, iface_id, iface.stats)
            upsert_proc_values(conn, iface_id, iface.name)

    logger.log(f"Collected {len(interfaces)} network interfaces.", source=LOG_SOURCE)


def main() -> None:
    """Run the interface collection loop forever."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    logger.log(f"Starting network interface daemon with {COLLECT_INTERVAL_SECONDS}s interval.", source=LOG_SOURCE)

    conn = db.connect(IFACE_DB_PATH)
    
    try:
        while True:
            try:
                collect_once(conn)
            except Exception as exc:  # noqa: BLE001 - daemon must keep running.
                logger.error(f"Collection failed: {exc}", source=LOG_SOURCE)
            time.sleep(COLLECT_INTERVAL_SECONDS)
    finally:
        db.close(conn)


if __name__ == "__main__":
    main()
