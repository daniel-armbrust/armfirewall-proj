"""Constants used by the ArmFirewall interface daemon."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
COLLECT_INTERVAL_SECONDS = int(os.environ.get("ARMFIREWALL_IFACED_INTERVAL", "10"))
LOG_SOURCE = "ifaced.py"

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
