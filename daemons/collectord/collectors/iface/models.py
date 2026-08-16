"""Data models for network interface collection."""

from __future__ import annotations

from dataclasses import dataclass, field


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
