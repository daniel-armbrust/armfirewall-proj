#!/usr/bin/env python3
"""Apply delegated IPv6 prefixes reported by odhcp6c."""

from __future__ import annotations

import ipaddress
import os
import subprocess
import sys
from pathlib import Path

LAN = os.environ["ARMFW_IPV6PD_LAN"]
SUBNET_ID = int(os.environ.get("ARMFW_IPV6PD_SUBNET_ID", "0"))
STATE = Path(os.environ.get("ARMFW_IPV6PD_RUNTIME_DIR", "/run/armfirewall/ipv6pd")) / "delegated-prefix"


def clear() -> None:
    if STATE.exists():
        subprocess.run(["ip", "-6", "addr", "del", f"{STATE.read_text().strip()}/64", "dev", LAN], check=False)
        STATE.unlink()


def main() -> None:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    if event in {"deconfig", "stopped"}:
        clear()
        return
    if event not in {"bound", "updated", "ra-updated"}:
        return
    prefix = os.environ.get("PREFIXES", "").split(maxsplit=1)[0].split(",", 1)[0]
    if not prefix:
        return
    network = ipaddress.IPv6Network(prefix, strict=False)
    if network.prefixlen > 64:
        raise RuntimeError("Provider delegated a prefix longer than /64")
    if SUBNET_ID >= 1 << (64 - network.prefixlen):
        raise RuntimeError("IPv6 PD subnet id is outside the delegated prefix")
    address = str(ipaddress.IPv6Address(int(network.network_address) + (SUBNET_ID << 64) + 1))
    clear()
    subprocess.run(["ip", "-6", "addr", "replace", f"{address}/64", "dev", LAN, "preferred_lft", "forever", "valid_lft", "forever"], check=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(address + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
