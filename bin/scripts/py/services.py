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


def script_dir() -> Path:
    """Return the directory where this script is located."""
    return Path(__file__).resolve().parent


def bin_dir() -> Path:
    """Return the ArmFirewall bin directory for this CLI."""
    return script_dir().parents[1]


def globals_path() -> Path:
    """Return the path to the ArmFirewall shell globals file."""
    return bin_dir() / "scripts" / "common" / "globals.sh"


def load_shell_globals() -> dict[str, str]:
    """Load paths from bin/scripts/common/globals.sh."""
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
    """Configure imports and database path overrides from globals.sh."""
    root_dir = Path(globals_values["ROOT_DIR"])
    db_dir = Path(globals_values["DB_DIR"])

    os.environ["ROOT_DIR"] = str(root_dir)
    os.environ["DB_DIR"] = str(db_dir)
    os.environ.setdefault("ARMFW_SERVICES_DB_PATH", str(db_dir / "services.db"))
    os.environ.setdefault("ARMFW_WORK_REQUEST_DB_PATH", str(db_dir / "work-requests.db"))

    root_text = str(root_dir)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    os.environ["PYTHONPATH"] = f"{root_text}{os.environ.get('PYTHONPATH', '') and ':' + os.environ['PYTHONPATH']}"
    return root_dir


def reexec_with_venv_python(root_dir: Path) -> None:
    """Re-execute the script with the project virtualenv Python when available."""
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
from core import constants as core_constants  # noqa: E402
from web.services import api as services_api  # noqa: E402
from web.services import catalog as services_catalog  # noqa: E402
from web.workrequests import api as workrequests_api  # noqa: E402

core_constants.SERVICES_DB_PATH = Path(os.environ["ARMFW_SERVICES_DB_PATH"])
core_constants.WORK_REQUEST_DB_PATH = Path(os.environ["ARMFW_WORK_REQUEST_DB_PATH"])
services_catalog.SERVICES_DB_PATH = core_constants.SERVICES_DB_PATH
workrequests_api.WORK_REQUEST_DB_PATH = core_constants.WORK_REQUEST_DB_PATH


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for service management."""
    examples = textwrap.dedent(
        """\
        Examples:
          services.sh list
          services.sh install dnsmasq
          services.sh uninstall bird
          services.sh restart armfirewall-api
          services.sh work-requests --limit 20
        """
    )
    parser = argparse.ArgumentParser(
        prog="services.sh",
        description="Install and manage ArmFirewall services.",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    list_parser = subparsers.add_parser("list", aliases=("status",), help="List main and optional services.")
    list_parser.add_argument("--json", action="store_true", help="Print the raw service status payload as JSON.")

    for command in ("install", "uninstall", "start", "stop", "restart"):
        command_parser = subparsers.add_parser(command, help=f"Queue service {command}.")
        command_parser.add_argument("service_name")

    work_parser = subparsers.add_parser("work-requests", help="List recent service work requests.")
    work_parser.add_argument("--limit", type=int, default=50)

    return parser


def print_json(data: Any) -> None:
    """Print a value as formatted JSON."""
    print(json.dumps(data, indent=2, sort_keys=True))


def queue_service_request(service_request: dict[str, Any]) -> dict[str, Any]:
    """Queue a service request using the same backend path as the GUI."""
    work_request_id = workrequests_api.queue_service_work_request(
        service_request["action"],
        service_request["payload"],
        category_name=service_request["category_name"],
    )
    return {
        "name": service_request["name"],
        "action": service_request["action"],
        "status": "queue",
        "work_request_id": work_request_id,
    }


def service_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a flat list of main and optional service rows."""
    rows: list[dict[str, Any]] = []
    for service in data.get("services", []):
        item = dict(service)
        item["group"] = "main"
        rows.append(item)
    for service in data.get("optional_services", []):
        item = dict(service)
        item["group"] = "optional"
        rows.append(item)
    return rows


def list_services(as_json: bool = False) -> None:
    """Print service status in a table or as JSON."""
    data = services_api.services_status()
    if as_json:
        print_json(data)
        return

    rows = service_rows(data)
    if not rows:
        print("No services configured.")
        return

    print("NAME                     GROUP     INSTALLED  STATE          DETAILS")
    for row in rows:
        installed = "yes" if row.get("installed") else "no"
        details = str(row.get("details") or row.get("description") or "-")
        print(
            f"{str(row.get('name'))[:24]:<24} "
            f"{str(row.get('group')):<9} "
            f"{installed:<10} "
            f"{str(row.get('state') or '-')[:14]:<14} "
            f"{details[:60]}"
        )


def run(args: argparse.Namespace) -> None:
    """Dispatch one service management command."""
    command = "list" if args.command == "status" else args.command

    if command == "list":
        list_services(args.json)
    elif command == "install":
        print_json(queue_service_request(services_api.install_optional_service(args.service_name)))
    elif command == "uninstall":
        print_json(queue_service_request(services_api.uninstall_optional_service(args.service_name)))
    elif command in {"start", "stop", "restart"}:
        print_json(queue_service_request(services_api.control_service(args.service_name, command)))
    elif command == "work-requests":
        print_json(workrequests_api.get_service_work_requests(args.limit))
    else:
        raise RuntimeError(f"Unsupported command: {command}")


def main() -> int:
    """Parse arguments, execute the command, and return a process exit code."""
    try:
        run(build_parser().parse_args())
    except (RuntimeError, ValueError, FileNotFoundError, db.DatabaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
