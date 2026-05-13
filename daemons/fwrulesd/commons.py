"""Shared iptables naming helpers used by firewall rule executors."""

from __future__ import annotations


def command_name(family: str) -> str:
    """Return the iptables command for one address family."""
    return "ip6tables" if family == "IPV6" else "iptables"
