"""Operating-system parsers for network interface collection."""

from __future__ import annotations

import ipaddress
import re
import subprocess

from core.process import run_command_stdout

from .models import InterfaceAddress, InterfaceInfo


def netmask_to_prefixlen(netmask: str) -> str:
    """Convert an IPv4 netmask to a prefix length."""
    try:
        return str(ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen)
    except ValueError:
        return ""


def read_ethtool_data(iface_name: str) -> tuple[int, str]:
    """Read link speed and duplex information from ethtool."""
    try:
        output = run_command_stdout(["ethtool", iface_name])
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0, "unknown"

    speed_match = re.search(r"Speed:\s+(\d+)Mb/s", output)
    duplex_match = re.search(r"Duplex:\s+(\w+)", output)
    speed = int(speed_match.group(1)) if speed_match else 0
    duplex_values = {"full": "full-duplex", "half": "half-duplex"}
    duplex = duplex_values.get(duplex_match.group(1).lower(), "unknown") if duplex_match else "unknown"
    return speed, duplex


def parse_ifconfig() -> list[InterfaceInfo]:
    """Parse ifconfig output into interface objects."""
    interfaces: list[InterfaceInfo] = []
    output = run_command_stdout(["ifconfig", "-a"])
    for block in re.split(r"\n\s*\n", output.strip()):
        lines = block.splitlines()
        if not lines:
            continue
        match = re.match(r"^([^:\s]+):\s+flags=\d+<([^>]*)>\s+mtu\s+(\d+)", lines[0])
        if not match:
            continue
        iface = InterfaceInfo(match.group(1), {item.strip() for item in match.group(2).split(",") if item.strip()}, int(match.group(3)))
        for raw_line in lines[1:]:
            line = raw_line.strip()
            if line.startswith("inet "):
                parts = line.split()
                iface.addresses.append(InterfaceAddress("ipv4", parts[1], netmask_to_prefixlen(parts[parts.index("netmask") + 1]) if "netmask" in parts else "", parts[parts.index("broadcast") + 1] if "broadcast" in parts else None))
            elif line.startswith("inet6 "):
                parts = line.split()
                iface.addresses.append(InterfaceAddress("ipv6", parts[1], parts[parts.index("prefixlen") + 1] if "prefixlen" in parts else "", scopeid=parts[parts.index("scopeid") + 1] if "scopeid" in parts else None))
            elif line.startswith("ether "):
                iface.mac_address = line.split()[1]
                type_match = re.search(r"\(([^)]+)\)", line)
                if type_match:
                    iface.type = type_match.group(1)
            elif line.startswith("loop "):
                iface.type = "Local Loopback"
            elif line.startswith("RX packets"):
                match = re.search(r"RX packets\s+(\d+)\s+bytes\s+(\d+)", line)
                if match:
                    iface.stats.rx_packets, iface.stats.rx_bytes = map(int, match.groups())
            elif line.startswith("RX errors"):
                fields = dict(re.findall(r"(errors|dropped|overruns|frame)\s+(\d+)", line))
                iface.stats.rx_errors, iface.stats.rx_dropped = int(fields.get("errors", 0)), int(fields.get("dropped", 0))
                iface.stats.rx_fifo, iface.stats.rx_frame = int(fields.get("overruns", 0)), int(fields.get("frame", 0))
            elif line.startswith("TX packets"):
                match = re.search(r"TX packets\s+(\d+)\s+bytes\s+(\d+)", line)
                if match:
                    iface.stats.tx_packets, iface.stats.tx_bytes = map(int, match.groups())
            elif line.startswith("TX errors"):
                fields = dict(re.findall(r"(errors|dropped|overruns|carrier|collisions)\s+(\d+)", line))
                iface.stats.tx_errors, iface.stats.tx_dropped = int(fields.get("errors", 0)), int(fields.get("dropped", 0))
                iface.stats.tx_fifo, iface.stats.tx_carrier = int(fields.get("overruns", 0)), int(fields.get("carrier", 0))
                iface.stats.tx_collisions = int(fields.get("collisions", 0))
        iface.speed_mbps, iface.duplex = read_ethtool_data(iface.name)
        interfaces.append(iface)
    return interfaces
