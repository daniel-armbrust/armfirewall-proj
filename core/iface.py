from __future__ import annotations

import ipaddress
from typing import Any

from core import db
from core.constants import IFACE_DB_PATH


def fetch_iface_rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Run a query against iface.db."""
    return db.fetch_all(query, params, db_path=IFACE_DB_PATH)


def get_role_config() -> dict[str, str]:
    """Return LAN and WAN interface names persisted in iface.db."""
    values: dict[str, str] = {}
    
    try:
        rows = fetch_iface_rows(
            """
            SELECT role, name
            FROM ifaces
            WHERE role IN ('LAN', 'WAN')
            ORDER BY CASE role WHEN 'LAN' THEN 0 WHEN 'WAN' THEN 1 ELSE 2 END, id
            """
        )
    except (FileNotFoundError, db.DatabaseError):
        return values

    for row in rows:
        key = "lan_iface" if row["role"] == "LAN" else "wan_iface"
        values.setdefault(key, str(row["name"]))
    
    return values


def get_lan_interface_names() -> list[str]:
    """Return every interface explicitly assigned the LAN role."""
    try:
        rows = fetch_iface_rows(
            """
            SELECT name
            FROM ifaces
            WHERE role = 'LAN' AND name <> 'lo'
            ORDER BY id
            """
        )
    except (FileNotFoundError, db.DatabaseError):
        return []

    return [str(row["name"]) for row in rows if str(row["name"] or "").strip()]


def get_lan_dns_bind_hosts() -> list[str]:
    """Return loopback plus valid addresses assigned to interfaces with the LAN role."""
    hosts = ["127.0.0.1"]
    try:
        rows = fetch_iface_rows(
            """
            SELECT a.addr
            FROM ifaces i
            JOIN addresses a ON a.iface_id = i.id
            WHERE i.role = 'LAN' AND i.name <> 'lo'
            ORDER BY i.id, a.id
            """
        )
    except (FileNotFoundError, db.DatabaseError):
        return hosts

    for row in rows:
        address = str(row["addr"] or "").strip()
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if parsed.is_unspecified or parsed.is_loopback or parsed.is_multicast or parsed.is_link_local:
            continue
        normalized = str(parsed)
        if normalized not in hosts:
            hosts.append(normalized)
    return hosts


def get_lan_ipv4_addresses_by_interface() -> dict[str, list[str]]:
    """Return usable IPv4 LAN addresses keyed by interface name."""
    result: dict[str, list[str]] = {}
    try:
        rows = fetch_iface_rows("""SELECT i.name, a.addr FROM ifaces i JOIN addresses a ON a.iface_id=i.id WHERE i.role='LAN' AND a.addr_family='ipv4' AND i.name<>'lo' ORDER BY i.id, a.is_secondary, a.id""")
    except (FileNotFoundError, db.DatabaseError):
        return result
    for row in rows:
        try: address = ipaddress.IPv4Address(str(row["addr"] or ""))
        except ipaddress.AddressValueError: continue
        if address.is_loopback or address.is_unspecified: continue
        result.setdefault(str(row["name"]), []).append(str(address))
    return result


def get_lan_primary_ipv4_address() -> str | None:
    """Return the preferred LAN IPv4 address for router-facing defaults."""
    try:
        rows = fetch_iface_rows(
            """
            SELECT a.addr
            FROM ifaces i
            JOIN addresses a ON a.iface_id = i.id
            WHERE a.addr_family = 'ipv4'
              AND i.name <> 'lo'
            ORDER BY
                CASE i.role WHEN 'LAN' THEN 0 ELSE 1 END,
                CASE i.protected WHEN 1 THEN 0 ELSE 1 END,
                i.id,
                a.is_secondary,
                a.id
            """
        )
    except (FileNotFoundError, db.DatabaseError):
        return None

    for row in rows:
        address = str(row["addr"] or "").strip()
        try:
            parsed = ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError:
            continue
        if not parsed.is_loopback:
            return str(parsed)
    return None


def get_lan_primary_iface_name() -> str | None:
    """Return the preferred LAN interface name for service defaults."""
    try:
        rows = fetch_iface_rows(
            """
            SELECT i.name
            FROM ifaces i
            JOIN addresses a ON a.iface_id = i.id
            WHERE a.addr_family = 'ipv4'
              AND i.name <> 'lo'
            ORDER BY
                CASE i.role WHEN 'LAN' THEN 0 ELSE 1 END,
                CASE i.protected WHEN 1 THEN 0 ELSE 1 END,
                i.id,
                a.is_secondary,
                a.id
            """
        )
    except (FileNotFoundError, db.DatabaseError):
        return None

    for row in rows:
        iface_name = str(row["name"] or "").strip()
        if iface_name and not iface_name.startswith("armfw"):
            return iface_name
    return None


def bytes_label(value: int | None) -> str:
    """Format a byte count as a compact binary unit label."""
    number = float(value or 0)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    unit = 0

    while number >= 1024 and unit < len(units) - 1:
        number /= 1024
        unit += 1

    if unit == 0:
        return f"{int(number)} {units[unit]}"
    
    return f"{number:.1f} {units[unit]}"


def byte_label(value: int | None) -> str:
    """Return a compact byte label."""
    return bytes_label(value)


def get_interfaces() -> dict[str, Any]:
    """Return interface inventory enriched with addresses and labels."""
    interfaces = fetch_iface_rows(
        """
        SELECT
            i.id,
            i.name,
            i.is_actived,
            i.description,
            i.mtu,
            i.mac_address,
            i.role,
            i.type,
            i.speed_mbps,
            i.duplex,
            i.protected,
            i.collected_at,
            s.rx_bytes,
            s.rx_packets,
            s.rx_errors,
            s.rx_dropped,
            s.tx_bytes,
            s.tx_packets,
            s.tx_errors,
            s.tx_dropped,
            s.collected_at AS stats_collected_at
        FROM ifaces i
        LEFT JOIN stats s ON s.iface_id = i.id
        ORDER BY
            CASE i.role WHEN 'LAN' THEN 0 WHEN 'WAN' THEN 1 ELSE 2 END,
            i.name
        """
    )

    addresses = fetch_iface_rows(
        """
        SELECT
            iface_id,
            addr_family,
            addr,
            prefixlen,
            broadcast,
            scopeid
        FROM addresses
        ORDER BY addr_family, addr
        """
    )

    by_iface: dict[int, list[dict[str, Any]]] = {}

    for address in addresses:
        by_iface.setdefault(int(address["iface_id"]), []).append(address)

    for iface in interfaces:
        iface["addresses"] = by_iface.get(int(iface["id"]), [])
        iface["rx_label"] = bytes_label(iface.get("rx_bytes"))
        iface["tx_label"] = bytes_label(iface.get("tx_bytes"))

    return {"interfaces": interfaces}


def get_traffic_counters() -> dict[str, Any]:
    """Return summary and raw counters for all interfaces."""
    interfaces = get_interfaces()["interfaces"]
    active_count = sum(1 for item in interfaces if item.get("is_actived") == 1)
    newest = max((item.get("stats_collected_at") or "" for item in interfaces), default="")

    return {
        "summary": {
            "interfaces": len(interfaces),
            "active": active_count,
            "updated_at": newest,
        },
        "interfaces": interfaces,
    }


def get_proc_values() -> dict[str, Any]:
    """Return collected proc values joined with interface metadata."""
    rows = fetch_iface_rows(
        """
        SELECT
            p.id,
            p.iface_id,
            i.name AS iface_name,
            i.role AS iface_role,
            p.addr_family,
            p.proc_path,
            p.description,
            p.default_value,
            p.desired_value,
            p.collected_at,
            p.updated_at
        FROM proc p
        JOIN ifaces i ON i.id = p.iface_id
        ORDER BY i.name, p.addr_family, p.proc_path
        """
    )

    return {"proc": rows}


def update_proc_desired_value(iface_name: str, proc_path: str, desired_value: str) -> dict[str, Any]:
    """Update the desired proc value for a specific interface."""
    with db.transaction(IFACE_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            UPDATE proc
            SET desired_value = ?, updated_at = CURRENT_TIMESTAMP
            WHERE proc_path = ?
              AND iface_id = (
                  SELECT id
                  FROM ifaces
                  WHERE name = ?
              )
            """,
            (desired_value, proc_path, iface_name),
        )
        
        if cursor.rowcount == 0:
            raise LookupError("Proc value not found.")

        row = db.fetch_one_on(
            conn,
            """
            SELECT
                p.id,
                p.iface_id,
                i.name AS iface_name,
                i.role AS iface_role,
                p.addr_family,
                p.proc_path,
                p.description,
                p.default_value,
                p.desired_value,
                p.collected_at,
                p.updated_at
            FROM proc p
            JOIN ifaces i ON i.id = p.iface_id
            WHERE i.name = ?
              AND p.proc_path = ?
            """,
            (iface_name, proc_path),
        )

    if row is None:
        raise LookupError("Proc value not found.")

    return {"proc": dict(row)}
