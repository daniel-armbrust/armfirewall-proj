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
    "conn_name": "conn_name",
    "description": "description",
    "enabled": "enabled",
    "left": "left_addr",
    "left_id": "left_id",
    "right": "right_addr",
    "shared_secret": "shared_secret",
    "leftsubnet": "leftsubnet",
    "rightsubnet": "rightsubnet",
    "auto": "auto",
    "mark": "mark",
    "vti_interface": "vti_interface",
    "vti_addr": "vti_addr",
    "vti_routing": "vti_routing",
    "ikev2": "ikev2",
    "ike": "ike",
    "phase2alg": "phase2alg",
    "encapsulation": "encapsulation",
    "ikelifetime": "ikelifetime",
    "salifetime": "salifetime",
}

def script_dir() -> Path:
    """Return the directory where this script is located.

    How it works:
        Resolves the absolute path of the current file and returns its parent
        directory.

    Parameters:
        None.

    Returns:
        Path: absolute directory that contains libreswan.py.
    """
    return Path(__file__).resolve().parent

def globals_path() -> Path:
    """Build the path to the ArmFirewall global constants file.

    How it works:
        Uses this script's directory as the base and points to
        bin/scripts/common/globals.sh, which is the official source for
        constants such as ROOT_DIR and DB_DIR.

    Parameters:
        None.

    Returns:
        Path: expected absolute path to globals.sh.
    """
    return script_dir() / "scripts" / "common" / "globals.sh"

def load_shell_globals() -> dict[str, str]:
    """Load constants defined in bin/scripts/common/globals.sh.

    How it works:
        Runs a bash subprocess that sources globals.sh and prints the constants
        required by this CLI. The KEY=VALUE output is converted into a Python
        dictionary. If globals.sh does not exist or bash fails, the function
        raises an error.

    Parameters:
        None.

    Returns:
        dict[str, str]: dictionary containing ROOT_DIR, DB_DIR, CONF_DIR, and
        SUPERVISORD_CONF loaded from the shell.
    """
    path = globals_path()

    if not path.exists():
        raise RuntimeError(f"ArmFirewall globals file was not found: {path}")

    command = r"""
source "$1" >/dev/null
printf 'ROOT_DIR=%s\n' "$ROOT_DIR"
printf 'DB_DIR=%s\n' "$DB_DIR"
printf 'CONF_DIR=%s\n' "$CONF_DIR"
printf 'SUPERVISORD_CONF=%s\n' "$SUPERVISORD_CONF"
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
    """Configure the Python environment from ArmFirewall constants.

    How it works:
        Reads ROOT_DIR and DB_DIR loaded from globals.sh, exports those values
        into os.environ, sets the default Libreswan and Work Requests database
        paths when they were not already provided by environment variables, and
        adds ROOT_DIR to sys.path/PYTHONPATH so application modules can be
        imported.

    Parameters:
        globals_values (dict[str, str]): constants loaded from globals.sh.

    Returns:
        Path: absolute ROOT_DIR path configured for the process.
    """
    root_dir = Path(globals_values["ROOT_DIR"])
    db_dir = Path(globals_values["DB_DIR"])

    os.environ["ROOT_DIR"] = str(root_dir)
    os.environ["DB_DIR"] = str(db_dir)
    os.environ.setdefault("ARMFW_LIBRESWAN_DB_PATH", str(db_dir / "libreswan.db"))
    os.environ.setdefault("ARMFW_WORK_REQUEST_DB_PATH", str(db_dir / "work-requests.db"))

    root_text = str(root_dir)

    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    
    os.environ["PYTHONPATH"] = f"{root_text}{os.environ.get('PYTHONPATH', '') and ':' + os.environ['PYTHONPATH']}"
    
    return root_dir


def reexec_with_venv_python(root_dir: Path) -> None:
    """Re-execute the CLI with the project's virtualenv Python when available.

    How it works:
        Looks for .venv/bin/python under ROOT_DIR. If that interpreter exists
        and differs from the current Python executable, it replaces the current
        process with os.execve while preserving arguments and environment
        variables. If the virtualenv does not exist or is already in use, the
        function simply returns.

    Parameters:
        root_dir (Path): ArmFirewall project root directory.

    Returns:
        None: this function does not return a value. On successful re-exec, the
        current process is replaced.
    """
    venv_python = root_dir / ".venv" / "bin" / "python"

    if not venv_python.exists():
        return

    try:
        current = Path(sys.executable).resolve()
        target = venv_python.resolve()
    except OSError:
        return

    if current == target:
        return

    os.execve(str(target), [str(target), str(Path(__file__).resolve()), *sys.argv[1:]], os.environ)


GLOBALS = load_shell_globals()
ROOT_DIR = configure_environment(GLOBALS)
reexec_with_venv_python(ROOT_DIR)

from core import db  # noqa: E402
from web.services.libreswan import api  # noqa: E402

api.LIBRESWAN_DB_PATH = Path(os.environ["ARMFW_LIBRESWAN_DB_PATH"])
api.WORK_REQUEST_DB_PATH = Path(os.environ["ARMFW_WORK_REQUEST_DB_PATH"])


def add_connection_options(parser: argparse.ArgumentParser) -> None:
    """Add Libreswan connection options accepted by the web GUI to a parser.

    How it works:
        Registers every configurable VPN connection field in argparse,
        including left/right addresses, PSK, subnets, mark, VTI, IKE proposals,
        lifetimes, and flags such as ikev2, encapsulation, and vti_routing.
        Some fields use choices from the web GUI backend so command-line
        validation stays aligned with the web interface.

    Parameters:
        parser (argparse.ArgumentParser): parser or subparser that will receive
        the connection options.

    Returns:
        None: the parser is modified in place.
    """
    parser.add_argument("--conn-name")
    parser.add_argument("--description")
    parser.add_argument("--enabled", choices=("0", "1", "true", "false", "yes", "no", "on", "off"))
    parser.add_argument("--left")
    parser.add_argument("--left-id")
    parser.add_argument("--right")
    parser.add_argument("--shared-secret")
    parser.add_argument("--leftsubnet")
    parser.add_argument("--rightsubnet")
    parser.add_argument("--auto", choices=sorted(api.AUTO_VALUES))
    parser.add_argument("--mark")
    parser.add_argument("--vti-interface")
    parser.add_argument("--vti-addr")
    parser.add_argument("--vti-routing", choices=sorted(api.YES_NO_VALUES))
    parser.add_argument("--ikev2", choices=sorted(api.IKEV2_VALUES))
    parser.add_argument("--ike")
    parser.add_argument("--phase2alg")
    parser.add_argument("--encapsulation", choices=sorted(api.ENCAPSULATION_VALUES))
    parser.add_argument("--ikelifetime")
    parser.add_argument("--salifetime")


def build_parser() -> argparse.ArgumentParser:
    """Create the main Libreswan command-line parser.

    How it works:
        Defines the root command, description, usage example, and supported
        subcommands: add/create, update, delete, enable, disable, show, and
        list. The add and update subcommands receive the same connection
        options as the GUI through add_connection_options.

    Parameters:
        None.

    Returns:
        argparse.ArgumentParser: parser configured to parse CLI arguments.
    """
    examples = textwrap.dedent(
        """\
        Examples:
          libreswan.py add \\
            --conn-name oracle-1 \\
            --left 10.100.10.3 \\
            --right 129.148.17.5 \\
            --left-id 137.131.222.14 \\
            --shared-secret secret \\
            --ikev2 insist \\
            --vti-addr 169.254.10.2/30

          libreswan.py update --id 1 --ikev2 insist --vti-routing yes
          libreswan.py list
          libreswan.py show --id 1
        """
    )
    root = argparse.ArgumentParser(
        prog="libreswan.py",
        description="Create and manage ArmFirewall Libreswan VPN connections.",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = root.add_subparsers(dest="command", metavar="COMMAND", required=True)

    add_parser = subparsers.add_parser(
        "add",
        aliases=("create",),
        help="Create a Libreswan connection and queue configuration apply.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_connection_options(add_parser)

    update_parser = subparsers.add_parser(
        "update",
        help="Update a Libreswan connection and queue configuration apply.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    update_parser.add_argument("--id", type=int, required=True)
    add_connection_options(update_parser)

    command_help = {
        "delete": "Delete a Libreswan connection and queue configuration apply.",
        "enable": "Enable a Libreswan connection and queue configuration apply.",
        "disable": "Disable a Libreswan connection and queue configuration apply.",
        "show": "Print one Libreswan connection as JSON.",
    }
    for command, help_text in command_help.items():
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("--id", type=int, required=True)

    subparsers.add_parser("list", help="List Libreswan connections.")

    return root


def payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Convert CLI arguments into a payload compatible with the GUI API.

    How it works:
        Iterates over FIELD_OPTIONS, reads each attribute from argparse.Namespace,
        and builds a dictionary using the field names expected by
        web.services.libreswan.api. Unprovided fields are omitted so defaults
        and existing values can be preserved by higher-level flows.

    Parameters:
        args (argparse.Namespace): arguments already parsed by argparse.

    Returns:
        dict[str, Any]: payload containing the user-provided fields, ready for
        create_connection or update_connection.
    """
    payload: dict[str, Any] = {}
    values = vars(args)

    for option_name, payload_name in FIELD_OPTIONS.items():
        value = values.get(option_name)

        if value is not None:
            payload[payload_name] = value

    return payload


def connection_by_id(connection_id: int) -> dict[str, Any]:
    """Fetch one Libreswan connection by ID from SQLite.

    How it works:
        Ensures the Libreswan schema is up to date, queries the
        libreswan_connections table by the provided ID, and converts the SQLite
        row into a dictionary. If the connection does not exist, it raises
        ValueError so the caller can turn it into a CLI error message.

    Parameters:
        connection_id (int): Libreswan connection ID to fetch.

    Returns:
        dict[str, Any]: complete data for the matching connection.
    """
    api.ensure_libreswan_schema()

    row = db.fetch_one(
        "SELECT * FROM libreswan_connections WHERE id = ?",
        (connection_id,),
        db_path=api.LIBRESWAN_DB_PATH,
    )

    if row is None:
        raise ValueError("Libreswan connection was not found.")
    
    return db.row_to_dict(row)


def update_payload(connection_id: int, args: argparse.Namespace) -> dict[str, Any]:
    """Build the complete payload used to update an existing connection.

    How it works:
        Loads the current connection by ID, copies every backend-supported field
        except authby, and overlays only the values provided by the CLI. This
        allows updating a single parameter without losing other values already
        stored in the database.

    Parameters:
        connection_id (int): ID of the connection being updated.
        args (argparse.Namespace): parsed command-line arguments.

    Returns:
        dict[str, Any]: complete normalized payload for api.update_connection.
    """
    current = connection_by_id(connection_id)
    payload = {field: current.get(field, "") for field in api.CONNECTION_FIELDS if field != "authby"}
    payload.update(payload_from_args(args))
    
    return payload


def print_json(data: Any) -> None:
    """Print a Python structure as formatted JSON.

    How it works:
        Serializes the received value with indentation and sorted keys, making
        responses from create, update, delete, enable, disable, and show easier
        to read.

    Parameters:
        data (Any): any JSON-serializable structure.

    Returns:
        None: the result is written to stdout.
    """
    print(json.dumps(data, indent=2, sort_keys=True))


def list_connections() -> None:
    """List Libreswan connections in a terminal-friendly table.

    How it works:
        Uses the same API as the GUI to retrieve connections and IPsec status,
        prints a message when no connections exist, or renders a compact table
        with ID, name, enabled flag, IPsec state, left/right endpoints, and VTI
        interface/address.

    Parameters:
        None.

    Returns:
        None: the listing is written to stdout.
    """
    data = api.list_connections()
    rows = data.get("connections", [])

    if not rows:
        print("No Libreswan connections configured.")
        return
    
    print("ID  NAME                 ENABLED  IPSEC  LEFT                 RIGHT                VTI")
    
    for row in rows:
        vti_addr = f"/{row['vti_addr']}" if row.get("vti_addr") else ""
        
        print(
            f"{row['id']:<3} "
            f"{str(row['conn_name'])[:20]:<20} "
            f"{'yes' if int(row['enabled']) == 1 else 'no':<7} "
            f"{str(row.get('ipsec_status', 'down')).upper():<6} "
            f"{str(row['left_addr'])[:20]:<20} "
            f"{str(row['right_addr'])[:20]:<20} "
            f"{row['vti_interface']}{vti_addr}"
        )


def run(args: argparse.Namespace) -> None:
    """Execute the subcommand requested by the user.

    How it works:
        Normalizes the create alias to add and dispatches the command to the
        appropriate Libreswan backend function. Write operations call the same
        API used by the web interface, so they write to SQLite and enqueue Work
        Requests in the same way. Read operations print data as JSON or a table.

    Parameters:
        args (argparse.Namespace): parsed arguments containing command and the
        subcommand-specific parameters.

    Returns:
        None: results are written to stdout; errors are propagated for main to
        handle.
    """
    command = "add" if args.command == "create" else args.command

    if command == "add":
        print_json(api.create_connection(payload_from_args(args)))
    elif command == "update":
        print_json(api.update_connection(args.id, update_payload(args.id, args)))
    elif command == "delete":
        print_json(api.delete_connection(args.id))
    elif command == "enable":
        print_json(api.set_connection_enabled(args.id, True))
    elif command == "disable":
        print_json(api.set_connection_enabled(args.id, False))
    elif command == "show":
        print_json(connection_by_id(args.id))
    elif command == "list":
        list_connections()
    else:
        raise RuntimeError(f"Unsupported command: {command}")


def main() -> int:
    """Main entry point for the Libreswan CLI.

    How it works:
        Builds the parser, parses sys.argv, executes the requested subcommand,
        and converts expected exceptions into stderr messages. The exit code
        follows CLI conventions: zero for success and one for a known failure.

    Parameters:
        None.

    Returns:
        int: process exit code, 0 for success and 1 for error.
    """
    try:
        run(build_parser().parse_args())
    except (RuntimeError, ValueError, db.DatabaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
