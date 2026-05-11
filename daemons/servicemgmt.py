#!/usr/bin/env python3
"""One-shot optional service package manager used by the work request daemon."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import log as logger


SUPERVISOR_CONF = ROOT_DIR / "conf" / "supervisord.conf"
LOG_SOURCE = "servicemgmt.py"
ALLOWED_SERVICES = {
    "armfirewall-squid": {
        "package": "squid",
        "binary": "/usr/sbin/squid",
    },
}


def command_exists(command: str) -> bool:
    """Return whether one command exists in PATH."""
    return shutil.which(command) is not None


def run_command(command: list[str], timeout: int = 300, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a bounded command and optionally raise with command output."""
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "command failed").strip()
        raise RuntimeError(f"{' '.join(command)}: {output}")
    return completed


def package_manager_command(operation: str, package: str) -> list[str]:
    """Build a package manager command for install or uninstall."""
    if operation not in {"install", "uninstall"}:
        raise RuntimeError(f"Unsupported package operation: {operation}")

    if command_exists("dnf"):
        return ["dnf", "-y", "install" if operation == "install" else "remove", package]
    if command_exists("yum"):
        return ["yum", "-y", "install" if operation == "install" else "remove", package]
    if command_exists("apt-get"):
        return ["apt-get", "-y", "install" if operation == "install" else "remove", package]
    raise RuntimeError("No supported package manager was found.")


def package_installed(package: str) -> bool:
    """Return whether a package is currently installed."""
    if command_exists("rpm"):
        return run_command(["rpm", "-q", package], timeout=30, check=False).returncode == 0
    if command_exists("dpkg-query"):
        completed = run_command(["dpkg-query", "-W", "-f=${Status}", package], timeout=30, check=False)
        return completed.returncode == 0 and "install ok installed" in completed.stdout
    return False


def payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Decode the work request JSON payload."""
    try:
        payload = json.loads(args.payload_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Payload JSON must decode to an object.")
    return payload


def validate_service(payload: dict[str, Any]) -> dict[str, Any]:
    """Return validated metadata for an allowed optional service."""
    service_name = str(payload.get("service_name") or "").strip()
    service = ALLOWED_SERVICES.get(service_name)
    if service is None:
        raise RuntimeError(f"Unsupported optional service: {service_name}")

    package = str(payload.get("package") or "").strip()
    if package != service["package"]:
        raise RuntimeError(f"Invalid package for {service_name}: {package}")

    return {
        "name": service_name,
        "package": package,
        "binary": service["binary"],
        "supervisor_program": str(payload.get("supervisor_program") or "").strip(),
    }


def supervisor_command(*args: str, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run supervisorctl against the ArmFirewall supervisor configuration."""
    if not command_exists("supervisorctl"):
        raise RuntimeError("supervisorctl was not found.")
    return run_command(["supervisorctl", "-c", str(SUPERVISOR_CONF), *args], timeout=timeout, check=check)


def supervisor_program_exists(service_name: str) -> bool:
    """Return whether a supervisor program section exists."""
    if not SUPERVISOR_CONF.exists():
        return False
    return f"[program:{service_name}]" in SUPERVISOR_CONF.read_text(encoding="utf-8")


def register_supervisor_program(service: dict[str, Any]) -> None:
    """Append the optional service supervisor program when missing."""
    if not SUPERVISOR_CONF.exists():
        raise RuntimeError(f"ArmFirewall supervisord.conf was not found: {SUPERVISOR_CONF}")
    if supervisor_program_exists(service["name"]):
        return
    program = str(service.get("supervisor_program") or "").strip()
    if not program.startswith(f"[program:{service['name']}]"):
        raise RuntimeError(f"Invalid supervisor program payload for {service['name']}.")
    with SUPERVISOR_CONF.open("a", encoding="utf-8") as handle:
        handle.write("\n")
        handle.write(program.format(root=ROOT_DIR))
        handle.write("\n")


def remove_supervisor_program(service_name: str) -> None:
    """Remove one optional service supervisor program section."""
    if not SUPERVISOR_CONF.exists():
        raise RuntimeError(f"ArmFirewall supervisord.conf was not found: {SUPERVISOR_CONF}")
    lines = SUPERVISOR_CONF.read_text(encoding="utf-8").splitlines()
    section = f"[program:{service_name}]"
    output: list[str] = []
    skip = False
    removed = False
    for line in lines:
        if line.strip() == section:
            skip = True
            removed = True
            continue
        if skip and line.startswith("[") and line.endswith("]"):
            skip = False
        if not skip:
            output.append(line)
    if removed:
        SUPERVISOR_CONF.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def install_service(service: dict[str, Any]) -> None:
    """Install a package and register its supervisor program."""
    if not package_installed(service["package"]):
        run_command(package_manager_command("install", service["package"]), timeout=600)
    register_supervisor_program(service)
    supervisor_command("reread", check=False)
    supervisor_command("update", check=False)
    logger.log(f"Installed optional service {service['name']}.", source=LOG_SOURCE)


def uninstall_service(service: dict[str, Any]) -> None:
    """Stop, unregister, and remove one optional service package."""
    if supervisor_program_exists(service["name"]):
        supervisor_command("stop", service["name"], check=False)
        remove_supervisor_program(service["name"])
        supervisor_command("reread", check=False)
        supervisor_command("update", check=False)
    if package_installed(service["package"]):
        run_command(package_manager_command("uninstall", service["package"]), timeout=600)
    logger.log(f"Uninstalled optional service {service['name']}.", source=LOG_SOURCE)


def build_parser() -> argparse.ArgumentParser:
    """Build the work request executor argument parser."""
    parser = argparse.ArgumentParser(description="ArmFirewall optional service package executor.")
    parser.add_argument("--work-request-id", required=True)
    parser.add_argument("--request-uid", required=True)
    parser.add_argument("--category-name", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--family", required=False)
    parser.add_argument("--target-name", required=True)
    parser.add_argument("--action-name", required=True)
    parser.add_argument("--target-rule-id", required=False)
    parser.add_argument("--payload-json", required=True)
    return parser


def main() -> int:
    """Execute one service management work request."""
    args = build_parser().parse_args()
    if args.category != "SERVICE_MANAGEMENT":
        raise RuntimeError(f"Unsupported category for servicemgmt.py: {args.category}")
    payload = payload_from_args(args)
    service = validate_service(payload)

    if args.action_name == "install":
        install_service(service)
    elif args.action_name == "uninstall":
        uninstall_service(service)
    else:
        raise RuntimeError(f"Unsupported service management action: {args.action_name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd captures stderr.
        logger.error(str(exc), source=LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        sys.exit(1)
