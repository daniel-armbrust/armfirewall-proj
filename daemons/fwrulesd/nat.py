"""NAT table rule helpers for the firewall rule executor."""

from __future__ import annotations

from typing import Any


def is_real_port(value: Any) -> bool:
    """Return whether a port value should be added to iptables."""
    if value is None:
        return False
    
    text = str(value).strip()

    return bool(text and text != "0")


def rule_action(rule: dict[str, Any]) -> str:
    """Return the NAT target action for one rule."""
    return str(rule.get("nat_action") or "ACCEPT").upper()


def add_target_options(command: list[str], action: str, rule: dict[str, Any]) -> None:
    """Append target-specific NAT options."""
    to_addr = rule.get("to_addr")
    to_port = rule.get("to_port")

    if action == "DNAT" and to_addr:
        value = str(to_addr)

        if is_real_port(to_port):
            value = f"{value}:{to_port}"

        command.extend(["--to-destination", value])
    elif action == "SNAT" and to_addr:
        value = str(to_addr)

        if is_real_port(to_port):
            value = f"{value}:{to_port}"

        command.extend(["--to-source", value])
    elif action == "REDIRECT" and is_real_port(to_port):
        command.extend(["--to-ports", str(to_port)])
