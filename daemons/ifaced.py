#!/usr/bin/env python3
"""Persistent daemon that collects network interface data into iface.db."""

from __future__ import annotations

import ipaddress
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import db
from core import log as logger

COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFIREWALL_IFACED_INTERVAL", "10"))
LOG_SOURCE = "ifaced.py"

CONF_PATH = ROOT_DIR / "conf" / "armfw.conf"

PROC_ITEMS = [
    ("ipv4", "forwarding", "Enables IPv4 packet forwarding on this interface."),
    ("ipv4", "rp_filter", "Controls reverse path filtering for IPv4 packets."),
    ("ipv4", "accept_redirects", "Controls whether ICMP redirect messages are accepted."),
    ("ipv4", "send_redirects", "Controls whether ICMP redirect messages are sent."),
    ("ipv4", "accept_source_route", "Controls whether source-routed IPv4 packets are accepted."),
    ("ipv4", "log_martians", "Controls logging of packets with impossible or suspicious source addresses."),
    ("ipv4", "arp_filter", "Controls whether ARP replies are filtered according to the route table."),
    ("ipv4", "arp_ignore", "Controls when the kernel replies to ARP requests for local addresses."),
    ("ipv4", "arp_announce", "Controls how local source IP addresses are announced in ARP requests."),
    ("ipv6", "disable_ipv6", "Controls whether IPv6 is disabled on this interface."),
    ("ipv6", "forwarding", "Enables IPv6 packet forwarding on this interface."),
    ("ipv6", "accept_redirects", "Controls whether ICMPv6 redirect messages are accepted."),
    ("ipv6", "accept_ra", "Controls whether IPv6 Router Advertisement messages are accepted."),
]


@dataclass
class InterfaceAddress:
    addr_family: str
    addr: str
    prefixlen: str
    broadcast: str | None = None
    scopeid: str | None = None
    is_secondary: int = 0
    iface_name_secondary: str | None = None


@dataclass
class InterfaceStats:
    rx_bytes: int = 0
    rx_packets: int = 0
    rx_errors: int = 0
    rx_dropped: int = 0
    rx_fifo: int = 0
    rx_frame: int = 0
    rx_multicast: int = 0
    tx_bytes: int = 0
    tx_packets: int = 0
    tx_errors: int = 0
    tx_dropped: int = 0
    tx_fifo: int = 0
    tx_collisions: int = 0
    tx_carrier: int = 0


@dataclass
class InterfaceInfo:
    name: str
    flags: set[str] = field(default_factory=set)
    mtu: int | None = None
    mac_address: str | None = None
    type: str = "Ethernet"
    speed_mbps: int = 0
    duplex: str = "unknown"
    addresses: list[InterfaceAddress] = field(default_factory=list)
    stats: InterfaceStats = field(default_factory=InterfaceStats)


def run_text(command: list[str]) -> str:
    """Run a command and return its standard output."""
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return completed.stdout


def read_hf_conf() -> dict[str, str]:
    """Read ArmFirewall key-value configuration."""
    values: dict[str, str] = {}
    if not CONF_PATH.exists():
        return values

    for line in CONF_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def netmask_to_prefixlen(netmask: str) -> str:
    """Convert an IPv4 netmask to a prefix length."""
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen)
    except ValueError:
        return ""


def parse_ifconfig() -> list[InterfaceInfo]:
    """Parse ifconfig output into interface objects."""
    output = run_text(["ifconfig", "-a"])
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
        output = run_text(["ethtool", iface_name])
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


def role_for_interface(iface_name: str, config: dict[str, str]) -> str:
    """Resolve the configured role for an interface name."""
    if iface_name == config.get("lan_iface"):
        return "LAN"
    if iface_name == config.get("wan_iface"):
        return "WAN"
    return "UNKNOWN"


def description_for_interface(iface_name: str, role: str) -> str:
    """Build a human-readable description for an interface."""
    if role == "LAN":
        return f"LAN interface configured in conf/armfw.conf: {iface_name}"
    if role == "WAN":
        return f"WAN interface configured in conf/armfw.conf: {iface_name}"
    return f"Network interface discovered by ifconfig -a: {iface_name}"


def upsert_iface(conn: db.Connection, iface: InterfaceInfo, role: str) -> int:
    """Insert or update the main interface row."""
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
            role = excluded.role,
            type = excluded.type,
            speed_mbps = excluded.speed_mbps,
            duplex = excluded.duplex,
            collected_at = CURRENT_TIMESTAMP
        """,
        (
            iface.name,
            1 if "UP" in iface.flags else 0,
            description_for_interface(iface.name, role),
            iface.mtu,
            iface.mac_address,
            role,
            iface.type,
            iface.speed_mbps,
            iface.duplex,
            1 if role in {"LAN", "WAN"} else 0,
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
    config = read_hf_conf()
    interfaces = parse_ifconfig()

    with conn:
        for iface in interfaces:
            role = role_for_interface(iface.name, config)
            iface_id = upsert_iface(conn, iface, role)
            replace_addresses(conn, iface_id, iface)
            upsert_stats(conn, iface_id, iface.stats)
            upsert_proc_values(conn, iface_id, iface.name)

    logger.log(f"Collected {len(interfaces)} network interfaces.", source=LOG_SOURCE)


def main() -> None:
    """Run the interface collection loop forever."""
    db.DB_DIR.mkdir(parents=True, exist_ok=True)
    logger.log(f"Starting network interface daemon with {COLLECT_INTERVAL_SECONDS}s interval.", source=LOG_SOURCE)

    conn = db.connect()
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
