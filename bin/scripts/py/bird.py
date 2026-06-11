#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any


FIELD_OPTIONS = {
    "enabled": "enabled",
    "protocol_name": "protocol_name",
    "description": "description",
    "source_address": "source_address",
    "local_as": "local_as",
    "neighbor_ip": "neighbor_ip",
    "neighbor_as": "neighbor_as",
    "iface_name": "iface_name",
    "session_type": "session_type",
    "direct": "direct",
    "multihop": "multihop",
    "multihop_ttl": "multihop_ttl",
    "passive": "passive",
    "password": "password",
    "import_policy": "import_policy",
    "export_policy": "export_policy",
}


def script_dir() -> Path:
    """Return the directory where this script is located."""
    return Path(__file__).resolve().parent


def bin_dir() -> Path:
    """Return the ArmFirewall bin directory for this CLI."""
    return script_dir().parents[1]


def globals_path() -> Path:
    """Build the path to the ArmFirewall global constants file."""
    return bin_dir() / "scripts" / "common" / "globals.sh"


def load_shell_globals() -> dict[str, str]:
    """Load constants defined in bin/scripts/common/globals.sh."""
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
    """Configure the Python environment from ArmFirewall constants."""
    root_dir = Path(globals_values["ROOT_DIR"])
    db_dir = Path(globals_values["DB_DIR"])
    conf_dir = Path(globals_values["CONF_DIR"])

    os.environ["ROOT_DIR"] = str(root_dir)
    os.environ["DB_DIR"] = str(db_dir)
    os.environ["CONF_DIR"] = str(conf_dir)
    os.environ.setdefault("ARMFW_BIRD_DB_PATH", str(db_dir / "bird.db"))
    os.environ.setdefault("ARMFW_WORK_REQUEST_DB_PATH", str(db_dir / "work-requests.db"))
    os.environ.setdefault("ARMFW_BIRD_CONFIG_PATH", str(conf_dir / "bird.conf"))

    root_text = str(root_dir)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    os.environ["PYTHONPATH"] = f"{root_text}{os.environ.get('PYTHONPATH', '') and ':' + os.environ['PYTHONPATH']}"
    return root_dir


def reexec_with_venv_python(root_dir: Path) -> None:
    """Re-execute the CLI with the project's virtualenv Python when available."""
    venv_dir = root_dir / ".venv"
    venv_python = venv_dir / "bin" / "python"
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
from web.services.routingprotocols import common as routing_common  # noqa: E402
from web.services.routingprotocols.bgp import api  # noqa: E402

routing_common.BIRD_DB_PATH = Path(os.environ["ARMFW_BIRD_DB_PATH"])
routing_common.WORK_REQUEST_DB_PATH = Path(os.environ["ARMFW_WORK_REQUEST_DB_PATH"])
routing_common.BIRD_CONFIG_PATH = Path(os.environ["ARMFW_BIRD_CONFIG_PATH"])
api.BIRD_DB_PATH = routing_common.BIRD_DB_PATH
api.WORK_REQUEST_DB_PATH = routing_common.WORK_REQUEST_DB_PATH
api.BIRD_CONFIG_PATH = routing_common.BIRD_CONFIG_PATH


BOOLEAN_CHOICES = ("0", "1", "true", "false", "yes", "no", "on", "off")
FAMILY_CHOICES = ("none", "ipv4", "ipv6", "ipv4/ipv6")


def add_bgp_options(parser: argparse.ArgumentParser) -> None:
    """Add BGP instance options accepted by the web GUI to a parser."""
    parser.add_argument("--enabled", choices=BOOLEAN_CHOICES, help="Enable or disable the BGP session.")
    parser.add_argument("--protocol-name", help="Optional display name for the BGP instance.")
    parser.add_argument("--description", help="Optional free-form description.")
    parser.add_argument("--source-address", help="Local source IP address used for the BGP session.")
    parser.add_argument("--local-as", help="Local ASN.")
    parser.add_argument("--neighbor-ip", help="Neighbor IP address.")
    parser.add_argument("--neighbor-as", help="Neighbor ASN.")
    parser.add_argument("--iface-name", help="Interface name used for direct sessions.")
    parser.add_argument(
        "--session-type",
        choices=sorted(routing_common.BIRD_BGP_SESSION_TYPES),
        help="Session type validation mode: auto, ebgp, or ibgp.",
    )
    parser.add_argument("--direct", choices=BOOLEAN_CHOICES, help="Render the session as direct when multihop is disabled.")
    parser.add_argument("--multihop", choices=BOOLEAN_CHOICES, help="Enable multihop mode for non-direct peers.")
    parser.add_argument("--multihop-ttl", help="Multihop TTL, used only when --multihop is enabled.")
    parser.add_argument("--passive", choices=BOOLEAN_CHOICES, help="Keep the session passive until the peer initiates it.")
    parser.add_argument("--password", help="Optional BGP MD5 password.")
    parser.add_argument("--import-policy", choices=FAMILY_CHOICES, help="Address families accepted from the peer.")
    parser.add_argument("--export-policy", choices=FAMILY_CHOICES, help="Address families announced to the peer.")


def build_parser() -> argparse.ArgumentParser:
    """Create the main BIRD/BGP command-line parser."""
    class BirdHelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
        pass

    examples = textwrap.dedent(
        """        Examples:
          bird.sh bgp add
            --protocol-name edge-oracle
            --description "Oracle OCI edge"
            --enabled yes
            --source-address 169.254.10.2
            --local-as 65001
            --neighbor-ip 169.254.10.1
            --neighbor-as 31898
            --iface-name vti1
            --session-type ebgp
            --direct yes
            --import-policy ipv4
            --export-policy none

          bird.sh bgp update --id 1 --multihop yes --multihop-ttl 32
          bird.sh bgp show --id 1
          bird.sh bgp list
        """
    )
    root = argparse.ArgumentParser(
        prog="bird.sh",
        description="Create and manage ArmFirewall BIRD BGP instances.",
        epilog=examples,
        formatter_class=BirdHelpFormatter,
    )
    section_parsers = root.add_subparsers(dest="section", metavar="SECTION", required=True)

    bgp_parser = section_parsers.add_parser(
        "bgp",
        help="Manage BIRD BGP instances.",
        description="Create, inspect, update, enable, disable, and delete managed BGP sessions.",
        formatter_class=BirdHelpFormatter,
    )
    subparsers = bgp_parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    add_parser = subparsers.add_parser(
        "add",
        aliases=("create",),
        help="Create a BGP instance and queue BIRD configuration apply.",
        description="Create one managed BGP session and queue a BIRD config apply work request.",
        formatter_class=BirdHelpFormatter,
    )
    add_bgp_options(add_parser)

    update_parser = subparsers.add_parser(
        "update",
        help="Update a BGP instance and queue BIRD configuration apply.",
        description="Update one managed BGP session and queue a BIRD config apply work request.",
        formatter_class=BirdHelpFormatter,
    )
    update_parser.add_argument("--id", type=int, required=True, help="Existing BGP instance ID.")
    add_bgp_options(update_parser)

    for command, help_text in {
        "delete": "Delete a BGP instance and queue BIRD configuration apply.",
        "enable": "Enable a BGP instance and queue BIRD configuration apply.",
        "disable": "Disable a BGP instance and queue BIRD configuration apply.",
        "show": "Print one BGP instance as JSON.",
    }.items():
        command_parser = subparsers.add_parser(command, help=help_text, formatter_class=BirdHelpFormatter)
        command_parser.add_argument("--id", type=int, required=True, help="Existing BGP instance ID.")

    subparsers.add_parser("list", help="List BGP instances.", formatter_class=BirdHelpFormatter)
    return root


def payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Convert CLI arguments into a payload compatible with the BGP GUI API."""
    payload: dict[str, Any] = {}
    values = vars(args)
    for option_name, payload_name in FIELD_OPTIONS.items():
        value = values.get(option_name)
        if value is not None:
            payload[payload_name] = value
    return payload


def bgp_instance_by_id(instance_id: int) -> dict[str, Any]:
    """Fetch one BGP instance by ID from bird.db."""
    settings = api.bgp_settings_from_db(instance_id)
    if settings.get("id") is None:
        raise ValueError("BGP instance was not found.")
    return settings


def update_payload(instance_id: int, args: argparse.Namespace) -> dict[str, Any]:
    """Build the complete payload used to update an existing BGP instance."""
    current = bgp_instance_by_id(instance_id)
    payload = {field: current.get(field, "") for field in FIELD_OPTIONS.values()}
    payload.update(payload_from_args(args))
    return payload


def print_json(data: Any) -> None:
    """Print a Python structure as formatted JSON."""
    print(json.dumps(data, indent=2, sort_keys=True))


def list_bgp_instances() -> None:
    """List BGP instances in a terminal-friendly table."""
    rows = api.list_bgp_settings_from_db()
    if not rows:
        print("No BGP instances configured.")
        return

    print("ID  NAME                 ENABLED  LOCAL_AS    NEIGHBOR                NEIGHBOR_AS  SESSION  IMPORT     EXPORT     IFACE")
    for row in rows:
        name = str(row.get("protocol_name") or (f"bgp{row['id']}"))
        iface_name = str(row.get("iface_name") or "-")
        print(
            f"{row['id']:<3} "
            f"{name[:20]:<20} "
            f"{'yes' if row.get('enabled') else 'no':<7} "
            f"{str(row.get('local_as') or '-')[:11]:<11} "
            f"{str(row.get('neighbor_ip') or '-')[:22]:<22} "
            f"{str(row.get('neighbor_as') or '-')[:12]:<12} "
            f"{str(row.get('session_type') or 'auto')[:8]:<8} "
            f"{str(row.get('import_policy') or 'none')[:10]:<10} "
            f"{str(row.get('export_policy') or 'none')[:10]:<10} "
            f"{iface_name[:16]}"
        )


def run(args: argparse.Namespace) -> None:
    """Execute the subcommand requested by the user."""
    if args.section != "bgp":
        raise RuntimeError(f"Unsupported section: {args.section}")

    command = "add" if args.command == "create" else args.command
    if command == "add":
        print_json(api.add_bgp_settings(payload_from_args(args)))
    elif command == "update":
        print_json(api.save_bgp_settings(update_payload(args.id, args), args.id))
    elif command == "delete":
        print_json(api.delete_bgp_settings(args.id))
    elif command == "enable":
        payload = update_payload(args.id, argparse.Namespace(**{**vars(args), "enabled": "true"}))
        print_json(api.save_bgp_settings(payload, args.id))
    elif command == "disable":
        payload = update_payload(args.id, argparse.Namespace(**{**vars(args), "enabled": "false"}))
        print_json(api.save_bgp_settings(payload, args.id))
    elif command == "show":
        print_json(bgp_instance_by_id(args.id))
    elif command == "list":
        list_bgp_instances()
    else:
        raise RuntimeError(f"Unsupported command: {command}")


def main() -> int:
    """Main entry point for the BIRD CLI."""
    try:
        run(build_parser().parse_args())
    except Exception as exc:  # keep CLI errors human-friendly like libreswan.py
        detail = getattr(exc, "detail", str(exc))
        print(f"error: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
