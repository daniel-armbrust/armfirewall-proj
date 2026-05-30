#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable


FIREWALL_DB_ENV = {
    ("FIREWALL_RULES", "IPV4"): "ARMFW_IPV4_FILTER_RULES_DB",
    ("FIREWALL_RULES", "IPV6"): "ARMFW_IPV6_FILTER_RULES_DB",
    ("NAT_RULES", "IPV4"): "ARMFW_IPV4_NAT_RULES_DB",
    ("NAT_RULES", "IPV6"): "ARMFW_IPV6_NAT_RULES_DB",
    ("MANGLE_RULES", "IPV4"): "ARMFW_IPV4_MANGLE_RULES_DB",
    ("MANGLE_RULES", "IPV6"): "ARMFW_IPV6_MANGLE_RULES_DB",
}

COMMON_RULE_FIELDS = {
    "family": "family",
    "chain": "chain",
    "iface_in": "iface_in",
    "iface_out": "iface_out",
    "src_addr": "src_addr",
    "src_port": "src_port",
    "dst_addr": "dst_addr",
    "dst_port": "dst_port",
    "protocol_name": "protocol_name",
    "protocol_type": "protocol_type",
    "protocol_code": "protocol_code",
    "enabled": "enabled",
}

FILTER_FIELDS = {
    **COMMON_RULE_FIELDS,
    "action": "action",
    "ct_new": "ct_new",
    "ct_established": "ct_established",
    "ct_related": "ct_related",
    "ct_invalid": "ct_invalid",
}

NAT_FIELDS = {
    **COMMON_RULE_FIELDS,
    "nat_action": "nat_action",
    "to_addr": "to_addr",
    "to_port": "to_port",
}

MANGLE_FIELDS = {
    **COMMON_RULE_FIELDS,
    "mangle_action": "mangle_action",
    "ct_new": "ct_new",
    "ct_established": "ct_established",
    "ct_related": "ct_related",
    "ct_invalid": "ct_invalid",
    "mark_value": "mark_value",
    "dscp_value": "dscp_value",
    "tos_value": "tos_value",
    "ttl_value": "ttl_value",
}


def script_dir() -> Path:
    """Return the directory where this script is located."""
    return Path(__file__).resolve().parent


def globals_path() -> Path:
    """Return the path to the ArmFirewall shell globals file."""
    return script_dir() / "scripts" / "common" / "globals.sh"


def load_shell_globals() -> dict[str, str]:
    """Load ROOT_DIR and DB_DIR from bin/scripts/common/globals.sh."""
    path = globals_path()
    if not path.exists():
        raise RuntimeError(f"ArmFirewall globals file was not found: {path}")

    command = """
source "$1" >/dev/null
printf "%s=%s\\n" ROOT_DIR "$ROOT_DIR"
printf "%s=%s\\n" DB_DIR "$DB_DIR"
printf "%s=%s\\n" CONF_DIR "$CONF_DIR"
printf "%s=%s\\n" SUPERVISORD_CONF "$SUPERVISORD_CONF"
"""
    completed = subprocess.run(
        ["bash", "-c", command, "armfw-globals", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def configure_environment(globals_values: dict[str, str]) -> Path:
    """Configure Python imports and default database paths from globals.sh."""
    root_dir = Path(globals_values["ROOT_DIR"])
    db_dir = Path(globals_values["DB_DIR"])

    os.environ["ROOT_DIR"] = str(root_dir)
    os.environ["DB_DIR"] = str(db_dir)
    os.environ.setdefault("ARMFW_WORK_REQUEST_DB_PATH", str(db_dir / "work-requests.db"))
    os.environ.setdefault("ARMFW_IPV4_FILTER_RULES_DB", str(db_dir / "ipv4-firewall-rules.db"))
    os.environ.setdefault("ARMFW_IPV6_FILTER_RULES_DB", str(db_dir / "ipv6-firewall-rules.db"))
    os.environ.setdefault("ARMFW_IPV4_NAT_RULES_DB", str(db_dir / "ipv4-nat-rules.db"))
    os.environ.setdefault("ARMFW_IPV6_NAT_RULES_DB", str(db_dir / "ipv6-nat-rules.db"))
    os.environ.setdefault("ARMFW_IPV4_MANGLE_RULES_DB", str(db_dir / "ipv4-mangle-rules.db"))
    os.environ.setdefault("ARMFW_IPV6_MANGLE_RULES_DB", str(db_dir / "ipv6-mangle-rules.db"))

    root_text = str(root_dir)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    os.environ["PYTHONPATH"] = f"{root_text}{os.environ.get('PYTHONPATH', '') and ':' + os.environ['PYTHONPATH']}"
    return root_dir


def reexec_with_venv_python(root_dir: Path) -> None:
    """Re-execute the script with the project virtualenv Python when available."""
    venv_dir = root_dir / ".venv"
    venv_python = root_dir / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return

    try:
        current_prefix = Path(sys.prefix).resolve()
        target_prefix = venv_dir.resolve()
    except OSError:
        return

    if current_prefix == target_prefix:
        return

    os.execve(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]], os.environ)


GLOBALS = load_shell_globals()
ROOT_DIR = configure_environment(GLOBALS)
reexec_with_venv_python(ROOT_DIR)

from core import db  # noqa: E402
from core import constants as core_constants  # noqa: E402
from daemons.fwrulesd import commons as fw_commons  # noqa: E402
from daemons.fwrulesd import constants as fw_constants  # noqa: E402
from daemons.fwrulesd.filter import rules as filter_core  # noqa: E402
from daemons.fwrulesd.mangle import rules as mangle_core  # noqa: E402
from daemons.fwrulesd.nat import rules as nat_core  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from web.firewall import api_filter_rules, api_mangle_rules, api_nat_rules  # noqa: E402


def configure_database_overrides() -> None:
    """Apply CLI database path overrides to firewall modules."""
    work_request_path = Path(os.environ["ARMFW_WORK_REQUEST_DB_PATH"])
    core_constants.WORK_REQUEST_DB_PATH = work_request_path
    fw_commons.WORK_REQUEST_DB_PATH = work_request_path
    filter_core.WORK_REQUEST_DB_PATH = work_request_path
    nat_core.WORK_REQUEST_DB_PATH = work_request_path
    mangle_core.WORK_REQUEST_DB_PATH = work_request_path
    for key, env_name in FIREWALL_DB_ENV.items():
        fw_constants.RULE_DATABASES[key] = Path(os.environ[env_name])

    fw_constants.FILTER_FAMILY_DATABASES.update(
        {
            "IPV4": fw_constants.RULE_DATABASES[("FIREWALL_RULES", "IPV4")],
            "IPV6": fw_constants.RULE_DATABASES[("FIREWALL_RULES", "IPV6")],
        }
    )
    fw_constants.NAT_FAMILY_DATABASES.update(
        {
            "IPV4": fw_constants.RULE_DATABASES[("NAT_RULES", "IPV4")],
            "IPV6": fw_constants.RULE_DATABASES[("NAT_RULES", "IPV6")],
        }
    )
    fw_constants.MANGLE_FAMILY_DATABASES.update(
        {
            "IPV4": fw_constants.RULE_DATABASES[("MANGLE_RULES", "IPV4")],
            "IPV6": fw_constants.RULE_DATABASES[("MANGLE_RULES", "IPV6")],
        }
    )


configure_database_overrides()


TABLE_APIS = {
    "filter": {
        "fields": FILTER_FIELDS,
        "list": api_filter_rules.get_filter_rules,
        "work": api_filter_rules.get_filter_work_requests,
        "show": api_filter_rules.get_filter_rule,
        "create": api_filter_rules.create_filter_rule,
        "update": api_filter_rules.update_filter_rule,
        "enable": api_filter_rules.set_filter_rule_enabled,
        "delete": api_filter_rules.delete_filter_rule,
        "apply": api_filter_rules.apply_filter_chain,
    },
    "nat": {
        "fields": NAT_FIELDS,
        "list": api_nat_rules.get_nat_rules,
        "work": api_nat_rules.get_nat_work_requests,
        "show": api_nat_rules.get_nat_rule,
        "create": api_nat_rules.create_nat_rule,
        "update": api_nat_rules.update_nat_rule,
        "enable": api_nat_rules.set_nat_rule_enabled,
        "delete": api_nat_rules.delete_nat_rule,
        "apply": api_nat_rules.apply_nat_chain,
    },
    "mangle": {
        "fields": MANGLE_FIELDS,
        "list": api_mangle_rules.get_mangle_rules,
        "work": api_mangle_rules.get_mangle_work_requests,
        "show": api_mangle_rules.get_mangle_rule,
        "create": api_mangle_rules.create_mangle_rule,
        "update": None,
        "enable": api_mangle_rules.set_mangle_rule_enabled,
        "delete": api_mangle_rules.delete_mangle_rule,
        "apply": api_mangle_rules.apply_mangle_chain,
    },
}


def add_common_rule_options(parser: argparse.ArgumentParser, include_identity: bool = True) -> None:
    """Add common firewall rule options to a subcommand parser."""
    if include_identity:
        parser.add_argument("--family", choices=("IPV4", "IPV6"), default="IPV4")
        parser.add_argument("--chain", required=True)
    parser.add_argument("--iface-in")
    parser.add_argument("--iface-out")
    parser.add_argument("--src-addr")
    parser.add_argument("--src-port")
    parser.add_argument("--dst-addr")
    parser.add_argument("--dst-port")
    parser.add_argument("--protocol-name", choices=("all", "tcp", "udp", "icmp", "icmpv6", "esp"))
    parser.add_argument("--protocol-type")
    parser.add_argument("--protocol-code")
    parser.add_argument("--enabled", choices=("0", "1", "true", "false", "yes", "no", "on", "off"))


def add_conntrack_options(parser: argparse.ArgumentParser) -> None:
    """Add conntrack options used by filter and mangle rules."""
    parser.add_argument("--conntrack-mode", choices=("none", "new", "established-related", "invalid"))
    parser.add_argument("--ct-new", choices=("0", "1"))
    parser.add_argument("--ct-established", choices=("0", "1"))
    parser.add_argument("--ct-related", choices=("0", "1"))
    parser.add_argument("--ct-invalid", choices=("0", "1"))


def add_rule_options(parser: argparse.ArgumentParser, table: str, include_identity: bool = True) -> None:
    """Add table-specific create/update options to a parser."""
    add_common_rule_options(parser, include_identity)
    if table == "filter":
        parser.add_argument("--action", choices=("ACCEPT", "DROP", "REJECT"), default="ACCEPT")
        add_conntrack_options(parser)
    elif table == "nat":
        parser.add_argument("--nat-action", choices=("DNAT", "SNAT", "MASQUERADE", "REDIRECT", "ACCEPT", "RETURN"), default="ACCEPT")
        parser.add_argument("--to-addr")
        parser.add_argument("--to-port")
    else:
        parser.add_argument("--mangle-action", choices=("MARK", "CONNMARK", "DSCP", "TOS", "TTL", "ACCEPT", "DROP", "RETURN"), default="ACCEPT")
        parser.add_argument("--mark-value")
        parser.add_argument("--dscp-value")
        parser.add_argument("--tos-value")
        parser.add_argument("--ttl-value")
        add_conntrack_options(parser)


def add_rule_identity_options(parser: argparse.ArgumentParser) -> None:
    """Add options that identify one persisted firewall rule."""
    parser.add_argument("--family", choices=("IPV4", "IPV6"), required=True)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--id", type=int, required=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for firewall rule management."""
    examples = textwrap.dedent(
        """\
        Examples:
          firewall.py filter add --chain INPUT --iface-in enp0s6 \\
            --protocol-name tcp --dst-port 22 --action ACCEPT --conntrack-mode new

          firewall.py filter apply --family IPV4 --chain INPUT
          firewall.py nat add --chain POSTROUTING --iface-out enp0s6 --nat-action MASQUERADE
          firewall.py mangle list --family IPV4 --chain PREROUTING
        """
    )
    root = argparse.ArgumentParser(
        prog="firewall.py",
        description="Create and manage ArmFirewall firewall rules.",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    table_parsers = root.add_subparsers(dest="table", metavar="TABLE", required=True)

    for table in ("filter", "nat", "mangle"):
        table_parser = table_parsers.add_parser(table, help=f"Manage {table} rules.")
        command_parsers = table_parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

        add_parser = command_parsers.add_parser("add", aliases=("create",), help=f"Create a {table} rule.")
        add_rule_options(add_parser, table)

        update_parser = command_parsers.add_parser("update", help=f"Update a {table} rule.")
        add_rule_identity_options(update_parser)
        add_rule_options(update_parser, table, include_identity=False)

        list_parser = command_parsers.add_parser("list", help=f"List {table} rules.")
        list_parser.add_argument("--family", choices=("IPV4", "IPV6"))
        list_parser.add_argument("--chain")

        show_parser = command_parsers.add_parser("show", help=f"Print one {table} rule as JSON.")
        add_rule_identity_options(show_parser)

        for command in ("enable", "disable", "delete"):
            command_parser = command_parsers.add_parser(command, help=f"{command.title()} one {table} rule.")
            add_rule_identity_options(command_parser)

        apply_parser = command_parsers.add_parser("apply", help=f"Queue apply for one {table} chain.")
        apply_parser.add_argument("--chain", required=True)
        apply_parser.add_argument("--family", choices=("IPV4", "IPV6"))

        command_parsers.add_parser("work-requests", help=f"List recent {table} work requests.")

    return root


def payload_from_args(args: argparse.Namespace, table: str) -> dict[str, Any]:
    """Convert argparse values into the payload expected by the web API."""
    values = vars(args)
    fields: dict[str, str] = TABLE_APIS[table]["fields"]  # type: ignore[assignment]
    payload = {payload_name: values[option_name] for option_name, payload_name in fields.items() if values.get(option_name) is not None}

    mode = values.get("conntrack_mode")
    if mode:
        payload.update({"ct_new": 0, "ct_established": 0, "ct_related": 0, "ct_invalid": 0})
        if mode == "new":
            payload["ct_new"] = 1
        elif mode == "established-related":
            payload["ct_established"] = 1
            payload["ct_related"] = 1
        elif mode == "invalid":
            payload["ct_invalid"] = 1

    return payload


def merged_update_payload(args: argparse.Namespace, table: str) -> dict[str, Any]:
    """Return the current rule data merged with CLI-provided update values."""
    current = TABLE_APIS[table]["show"](args.family, args.chain, args.id)  # type: ignore[operator]
    payload = dict(current)
    payload.update(payload_from_args(args, table))
    payload["family"] = args.family
    payload["chain"] = args.chain
    return payload


def filtered_rules(args: argparse.Namespace, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return rules filtered by optional family and chain arguments."""
    rules = list(data.get("rules", []))
    if getattr(args, "family", None):
        rules = [rule for rule in rules if rule.get("family") == args.family]
    if getattr(args, "chain", None):
        rules = [rule for rule in rules if rule.get("chain") == str(args.chain).upper()]
    return rules


def print_json(data: Any) -> None:
    """Print a Python value as formatted JSON."""
    print(json.dumps(data, indent=2, sort_keys=True))


def list_rules(args: argparse.Namespace, table: str) -> None:
    """Print firewall rules in a compact terminal table."""
    data = TABLE_APIS[table]["list"]()  # type: ignore[operator]
    rules = filtered_rules(args, data)
    if not rules:
        print(f"No {table} rules configured.")
        return

    print("ID  FAMILY  CHAIN        EN  STATE    ACTION       PROTO   SOURCE               DESTINATION          IFACES")
    for rule in rules:
        action = rule.get("action") or rule.get("nat_action") or rule.get("mangle_action") or "-"
        state = rule.get("apply_state", "pending")
        ifaces = f"in={rule.get('iface_in') or '*'} out={rule.get('iface_out') or '*'}"
        print(
            f"{rule['id']:<3} "
            f"{rule['family']:<6} "
            f"{rule['chain']:<12} "
            f"{'yes' if int(rule['enabled']) == 1 else 'no':<3} "
            f"{str(state)[:8]:<8} "
            f"{str(action)[:12]:<12} "
            f"{str(rule.get('protocol_name') or '-')[:7]:<7} "
            f"{str(rule.get('src_addr') or '-')[:20]:<20} "
            f"{str(rule.get('dst_addr') or '-')[:20]:<20} "
            f"{ifaces}"
        )


def run(args: argparse.Namespace) -> None:
    """Dispatch the requested table command to the corresponding web API."""
    table = args.table
    command = "add" if args.command == "create" else args.command
    table_api = TABLE_APIS[table]

    if command == "add":
        print_json(table_api["create"](payload_from_args(args, table)))  # type: ignore[operator]
    elif command == "update":
        if table_api["update"] is None:
            raise RuntimeError(f"{table} rule update is not supported.")
        print_json(table_api["update"](args.family, args.chain, args.id, merged_update_payload(args, table)))  # type: ignore[operator]
    elif command == "delete":
        print_json(table_api["delete"](args.family, args.chain, args.id))  # type: ignore[operator]
    elif command == "enable":
        print_json(table_api["enable"](args.family, args.chain, args.id, {"enabled": 1}))  # type: ignore[operator]
    elif command == "disable":
        print_json(table_api["enable"](args.family, args.chain, args.id, {"enabled": 0}))  # type: ignore[operator]
    elif command == "show":
        print_json(table_api["show"](args.family, args.chain, args.id))  # type: ignore[operator]
    elif command == "list":
        list_rules(args, table)
    elif command == "apply":
        print_json(table_api["apply"](args.chain, {"family": args.family} if args.family else {}))  # type: ignore[operator]
    elif command == "work-requests":
        print_json(table_api["work"]())  # type: ignore[operator]
    else:
        raise RuntimeError(f"Unsupported command: {command}")


def main() -> int:
    """Parse arguments, execute the command, and return a process exit code."""
    try:
        run(build_parser().parse_args())
    except HTTPException as exc:
        print(f"error: {exc.detail}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, db.DatabaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
