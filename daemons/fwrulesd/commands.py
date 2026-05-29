"""iptables/ip6tables command builders for firewall rule work requests."""

from __future__ import annotations

from typing import Any

from core.process import run_command

from .commons import command_name
from .constants import TABLE_METADATA, WILDCARD_ADDRESSES
from .filter import table as filter_table
from .mangle import table as mangle_table
from .nat import table as nat_table
from .repository import table_from_request


def add_if_value(command: list[str], flag: str, value: Any) -> None:
    """Append a command argument pair when the value is meaningful."""
    if value is None:
        return

    text = str(value).strip()

    if text and text.upper() != "ANY":
        command.extend([flag, text])


def add_address_match(command: list[str], flag: str, value: Any) -> None:
    """Append a source or destination address match when not wildcard."""
    if value in WILDCARD_ADDRESSES:
        return

    add_if_value(command, flag, value)


def is_real_port(value: Any) -> bool:
    """Return whether a port value should be added to iptables."""
    return nat_table.is_real_port(value)


def add_protocol_match(command: list[str], family: str, rule: dict[str, Any]) -> None:
    """Append protocol, port, and ICMP matches for one rule."""
    protocol = str(rule.get("protocol_name") or "all").lower()

    if protocol == "all":
        return

    iptables_protocol = "ipv6-icmp" if family == "IPV6" and protocol in {"icmp", "icmpv6"} else protocol
    command.extend(["-p", iptables_protocol])

    if protocol in {"tcp", "udp"}:
        if is_real_port(rule.get("src_port")):
            command.extend(["--sport", str(rule["src_port"])])
        if is_real_port(rule.get("dst_port")):
            command.extend(["--dport", str(rule["dst_port"])])
        return

    if protocol in {"icmp", "icmpv6"} and rule.get("protocol_type") is not None:
        icmp_flag = "--icmpv6-type" if family == "IPV6" else "--icmp-type"
        icmp_value = str(rule["protocol_type"])

        if rule.get("protocol_code") is not None:
            icmp_value = f"{icmp_value}/{rule['protocol_code']}"

        command.extend([icmp_flag, icmp_value])


def add_conntrack_match(command: list[str], rule: dict[str, Any]) -> None:
    """Append conntrack state matches for filter and mangle rules."""
    states = []

    for column, state in (
        ("ct_new", "NEW"),
        ("ct_established", "ESTABLISHED"),
        ("ct_related", "RELATED"),
        ("ct_invalid", "INVALID"),
    ):
        if int(rule.get(column) or 0) == 1:
            states.append(state)

    if states:
        command.extend(["-m", "conntrack", "--ctstate", ",".join(states)])


def add_interface_matches(command: list[str], chain: str, rule: dict[str, Any]) -> None:
    """Append input and output interface matches for the selected chain."""
    if chain in {"INPUT", "FORWARD", "PREROUTING"}:
        add_if_value(command, "-i", rule.get("iface_in"))

    if chain in {"OUTPUT", "FORWARD", "POSTROUTING"}:
        add_if_value(command, "-o", rule.get("iface_out"))


def rule_spec(args: Any, table: str, chain: str, rule: dict[str, Any]) -> list[str]:
    """Build the common iptables rule specification without operation."""
    family = args.family
    command = [command_name(family), "-t", table, chain]

    add_interface_matches(command, chain, rule)
    add_address_match(command, "-s", rule.get("src_addr"))
    add_address_match(command, "-d", rule.get("dst_addr"))
    add_protocol_match(command, family, rule)

    if table in {"filter", "mangle"}:
        add_conntrack_match(command, rule)

    if table == "filter":
        action = filter_table.rule_action(rule)
    elif table == "nat":
        action = nat_table.rule_action(rule)
    else:
        action = mangle_table.rule_action(rule)

    command.extend(["-j", action])

    if table == "nat":
        nat_table.add_target_options(command, action, rule)
    elif table == "mangle":
        mangle_table.add_target_options(command, action, rule)

    return command


def apply_rule(args: Any, rule: dict[str, Any]) -> bool:
    """Apply one rule when it is enabled and not already present."""
    if int(rule.get("enabled") or 0) == 0:
        return False

    table_name = table_from_request(args, rule)
    iptables_table, chain = TABLE_METADATA[table_name]
    spec = rule_spec(args, iptables_table, chain, rule)
    check_command = [*spec[:3], "-C", *spec[3:]]
    add_command = [*spec[:3], "-A", *spec[3:]]

    if run_command(check_command, check=False).returncode == 0:
        return False

    run_command(add_command)

    return True


def remove_rule(args: Any, rule: dict[str, Any]) -> int:
    """Remove all operating system copies matching one rule."""
    table_name = table_from_request(args, rule)
    iptables_table, chain = TABLE_METADATA[table_name]
    spec = rule_spec(args, iptables_table, chain, rule)
    delete_command = [*spec[:3], "-D", *spec[3:]]
    removed = 0

    while True:
        completed = run_command(delete_command, check=False)

        if completed.returncode != 0:
            break
        removed += 1

    return removed


def flush_chain(args: Any, table_name: str) -> None:
    """Flush one operating system chain before a full chain apply."""
    iptables_table, chain = TABLE_METADATA[table_name]

    run_command([command_name(args.family), "-t", iptables_table, "-F", chain])
