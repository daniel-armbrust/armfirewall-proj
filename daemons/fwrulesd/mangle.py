"""Mangle table rule helpers for the firewall rule executor."""

from __future__ import annotations

from typing import Any


def rule_action(rule: dict[str, Any]) -> str:
    """Return the mangle target action for one rule."""
    return str(rule.get("mangle_action") or "ACCEPT").upper()


def add_target_options(command: list[str], action: str, rule: dict[str, Any]) -> None:
    """Append target-specific mangle options."""
    if action in {"MARK", "CONNMARK"} and rule.get("mark_value"):
        option = "--set-mark" if action == "MARK" else "--set-xmark"
        command.extend([option, str(rule["mark_value"])])
    elif action == "DSCP" and rule.get("dscp_value"):
        command.extend(["--set-dscp", str(rule["dscp_value"])])
    elif action == "TOS" and rule.get("tos_value"):
        command.extend(["--set-tos", str(rule["tos_value"])])
    elif action == "TTL" and rule.get("ttl_value"):
        command.extend(["--ttl-set", str(rule["ttl_value"])])
