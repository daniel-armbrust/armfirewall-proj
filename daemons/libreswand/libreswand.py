#!/usr/bin/env python3
"""One-shot Libreswan configuration renderer used by the work request daemon."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from core import db
from core import log as logger
from core.payload import decode_json_payload
from core.process import command_exists, run_command

from .constants import (
    IPSEC_COMMAND,
    IPSEC_TIMEOUT_SECONDS,
    LIBRESWAN_CONFIG_DIR,
    LIBRESWAN_DB_PATH,
    LIBRESWAN_IPSEC_CONF,
    LIBRESWAN_SERVICE_NAME,
    LIBRESWAN_SECRETS,
    LOG_SOURCE,
    SUPERVISOR_CONF,
    SUPERVISOR_TIMEOUT_SECONDS,
    SUPERVISORCTL_COMMAND,
    WORK_REQUEST_DB_PATH,
)
from .models import LibreswanConnection, LibreswanWorkRequest


def request_from_args(args: argparse.Namespace) -> LibreswanWorkRequest:
    """Return a normalized Libreswan work request from CLI arguments."""
    return LibreswanWorkRequest(
        work_request_id=str(args.work_request_id),
        request_uid=str(args.request_uid),
        category_name=str(args.category_name),
        category=str(args.category),
        family=str(args.family or ""),
        target_name=str(args.target_name),
        action_name=str(args.action_name),
        target_rule_id=str(args.target_rule_id or ""),
        payload=decode_json_payload(args.payload_json),
    )


def validate_request(request: LibreswanWorkRequest) -> None:
    """Ensure this executor supports the requested Libreswan action."""
    if request.category != "SERVICE_MANAGEMENT" or request.target_name != "libreswan_config":
        raise RuntimeError(f"Unsupported category for libreswand.py: {request.category}/{request.target_name}")
    if request.action_name != "apply":
        raise RuntimeError(f"Unsupported Libreswan action: {request.action_name}")


def filename_slug(value: str) -> str:
    """Return a safe configuration filename stem for a connection name."""
    rendered = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return rendered.strip("._") or "connection"


def escape_psk(value: str) -> str:
    """Escape a pre-shared key for ipsec.secrets."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def left_secret_identity(conn: LibreswanConnection) -> str:
    """Return the local identity used to match the Libreswan PSK."""
    return conn.left_id.strip() or conn.left_addr


def ensure_libreswan_schema() -> None:
    """Apply lightweight Libreswan schema compatibility fixes."""
    with db.transaction(LIBRESWAN_DB_PATH) as conn:
        columns = {str(row["name"]) for row in db.execute_on(conn, "PRAGMA table_info(libreswan_connections)").fetchall()}
        if "vti_addr" not in columns:
            db.execute_on(conn, "ALTER TABLE libreswan_connections ADD COLUMN vti_addr TEXT NOT NULL DEFAULT ''")
        if "vti_mtu" not in columns:
            db.execute_on(conn, "ALTER TABLE libreswan_connections ADD COLUMN vti_mtu INTEGER NOT NULL DEFAULT 0")


def load_connections() -> list[LibreswanConnection]:
    """Return persisted Libreswan tunnel definitions."""
    ensure_libreswan_schema()

    rows = db.fetch_all(
        """
        SELECT *
        FROM libreswan_connections
        ORDER BY conn_name
        """,
        db_path=LIBRESWAN_DB_PATH,
    )
    return [LibreswanConnection.from_row(row) for row in rows]


def enabled_connections(connections: list[LibreswanConnection]) -> list[LibreswanConnection]:
    """Return enabled Libreswan tunnel definitions."""
    return [conn for conn in connections if conn.enabled == 1]


def render_connection_config(conn: LibreswanConnection) -> str:
    """Render one Libreswan tunnel configuration."""
    lines = [
        f"conn {conn.conn_name}",
        f"     left={conn.left_addr}",
    ]
    if conn.left_id:
        lines.append(f"     leftid={conn.left_id}")
    lines.extend(
        [
            f"     right={conn.right_addr}",
            f"     authby={conn.authby}",
            f"     leftsubnet={conn.leftsubnet}",
            f"     rightsubnet={conn.rightsubnet}",
            f"     auto={conn.auto}",
            f"     mark={conn.mark}",
            f"     vti-interface={conn.vti_interface}",
            f"     vti-routing={conn.vti_routing}",
            f"     ikev2={conn.ikev2}",
            f"     ike={conn.ike}",
            f"     phase2alg={conn.phase2alg}",
            f"     encapsulation={conn.encapsulation}",
            f"     ikelifetime={conn.ikelifetime}",
            f"     salifetime={conn.salifetime}",
        ]
    )
    if conn.vti_addr:
        lines.append(f"     leftvti={conn.vti_addr}")
    lines.append("")
    return "\n".join(lines)


def render_main_config(connections: list[LibreswanConnection]) -> str:
    """Render the managed Libreswan ipsec.conf file."""
    lines = [
        "# ArmFirewall managed Libreswan configuration.",
        "# Generated from Services / Libreswan.",
        "config setup",
        "",
    ]
    for conn in connections:
        lines.append(f"include {connection_config_path(conn)}")
    return "\n".join(lines).rstrip() + "\n"


def render_secrets(connections: list[LibreswanConnection]) -> str:
    """Render the managed Libreswan ipsec.secrets file."""
    lines = [
        "# ArmFirewall managed Libreswan secrets.",
        "# Generated from Services / Libreswan.",
    ]
    for conn in connections:
        lines.append(f'{left_secret_identity(conn)} {conn.right_addr} : PSK "{escape_psk(conn.shared_secret)}"')
    return "\n".join(lines).rstrip() + "\n"


def connection_config_path(conn: LibreswanConnection) -> Path:
    """Return the managed per-connection ipsec.conf path."""
    return connection_config_dir(conn) / "ipsec.conf"


def connection_config_dir(conn: LibreswanConnection) -> Path:
    """Return the managed per-connection configuration directory."""
    return LIBRESWAN_CONFIG_DIR / filename_slug(conn.conn_name)


def write_atomic(path: Path, content: str, *, mode: int | None = None) -> None:
    """Atomically write one text file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    if mode is not None:
        tmp_path.chmod(mode)
    tmp_path.replace(path)
    if mode is not None:
        path.chmod(mode)


def remove_stale_connection_files(active_paths: set[Path]) -> None:
    """Remove managed per-connection files that are no longer active."""
    if not LIBRESWAN_CONFIG_DIR.exists():
        return

    protected = {LIBRESWAN_IPSEC_CONF, LIBRESWAN_SECRETS, *active_paths}
    for path in LIBRESWAN_CONFIG_DIR.glob("*.conf"):
        if path not in protected:
            path.unlink()

    active_dirs = {path.parent for path in active_paths}
    for path in LIBRESWAN_CONFIG_DIR.iterdir():
        if not path.is_dir() or path in active_dirs:
            continue
        managed_config = path / "ipsec.conf"
        if managed_config.exists():
            managed_config.unlink()
        try:
            path.rmdir()
        except OSError:
            continue


def render_files(connections: list[LibreswanConnection]) -> list[LibreswanConnection]:
    """Render all managed Libreswan files and return enabled connections."""
    active_connections = enabled_connections(connections)
    active_paths = {connection_config_path(conn) for conn in active_connections}

    LIBRESWAN_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    remove_stale_connection_files(active_paths)

    for conn in active_connections:
        if not conn.shared_secret.strip():
            raise RuntimeError(f"Connection {conn.conn_name} has no shared secret.")
        write_atomic(connection_config_path(conn), render_connection_config(conn), mode=0o600)

    write_atomic(LIBRESWAN_IPSEC_CONF, render_main_config(active_connections), mode=0o600)
    write_atomic(LIBRESWAN_SECRETS, render_secrets(active_connections), mode=0o600)

    return active_connections


def run_ipsec(command: list[str], *, check: bool = True) -> None:
    """Run an ipsec command with the managed configuration path."""
    run_command([IPSEC_COMMAND, "auto", "--config", str(LIBRESWAN_IPSEC_CONF), *command], check=check, timeout=IPSEC_TIMEOUT_SECONDS)


def configure_vti_interface(conn: LibreswanConnection) -> None:
    """Apply configured IP address and MTU to the Libreswan VTI interface."""
    has_addr = bool(conn.vti_addr.strip())
    has_mtu = conn.vti_mtu > 0
    if not has_addr and not has_mtu:
        return

    if not command_exists("ip"):
        raise RuntimeError("ip command was not found.")

    interface_ready = False
    for attempt in range(10):
        show_result = run_command(["ip", "link", "show", "dev", conn.vti_interface], check=False, timeout=IPSEC_TIMEOUT_SECONDS)
        if show_result.returncode == 0:
            interface_ready = True
            break
        time.sleep(0.5)

    if not interface_ready:
        raise RuntimeError(f"VTI interface {conn.vti_interface} was not found.")

    stable_checks = 0
    required_stable_checks = 5
    for attempt in range(30):
        if has_addr:
            run_command(["ip", "addr", "replace", conn.vti_addr, "dev", conn.vti_interface], timeout=IPSEC_TIMEOUT_SECONDS)
        if has_mtu:
            run_command(["ip", "link", "set", "dev", conn.vti_interface, "mtu", str(conn.vti_mtu)], timeout=IPSEC_TIMEOUT_SECONDS)
        run_command(["ip", "link", "set", "dev", conn.vti_interface, "up"], timeout=IPSEC_TIMEOUT_SECONDS)

        if not has_mtu:
            stable_checks += 1
        else:
            link_result = run_command(["ip", "-o", "link", "show", "dev", conn.vti_interface], check=False, timeout=IPSEC_TIMEOUT_SECONDS)
            mtu_applied = f" mtu {conn.vti_mtu} " in f" {link_result.stdout.strip()} "
            stable_checks = stable_checks + 1 if mtu_applied else 0

        if stable_checks >= required_stable_checks:
            break
        if attempt < 29:
            time.sleep(0.5)

    if stable_checks < required_stable_checks:
        raise RuntimeError(f"VTI interface {conn.vti_interface} did not keep MTU {conn.vti_mtu}.")


def deactivate_previous_connection(request: LibreswanWorkRequest) -> None:
    """Ask Libreswan to unload a removed or renamed connection."""
    previous_name = str(request.payload.get("previous_conn_name") or "").strip()
    if not previous_name:
        return
    run_ipsec(["--delete", previous_name], check=False)


def activate_connections(connections: list[LibreswanConnection], request: LibreswanWorkRequest) -> None:
    """Load enabled Libreswan connections and start routed/start tunnels."""
    if not command_exists(IPSEC_COMMAND):
        raise RuntimeError("Libreswan ipsec command was not found.")

    deactivate_previous_connection(request)

    for conn in connections:
        run_ipsec(["--replace", conn.conn_name])
        activation_error: Exception | None = None
        try:
            if conn.auto == "start":
                run_ipsec(["--up", conn.conn_name])
            elif conn.auto in {"route", "ondemand"}:
                run_ipsec(["--route", conn.conn_name])
        except Exception as exc:
            activation_error = exc
        finally:
            try:
                configure_vti_interface(conn)
            except Exception as exc:
                logger.error(f"Could not configure VTI interface {conn.vti_interface}: {exc}", source=LOG_SOURCE)
                if activation_error is None:
                    raise
        if activation_error is not None:
            raise activation_error


def supervisorctl(command: str, *args: str, check: bool = True) -> str:
    """Run one supervisorctl command and return its output."""
    completed = run_command(
        [SUPERVISORCTL_COMMAND, "-c", str(SUPERVISOR_CONF), command, *args],
        check=check,
        timeout=SUPERVISOR_TIMEOUT_SECONDS,
    )
    return completed.stdout.strip()


def restart_libreswan_service() -> None:
    """Restart or start the Libreswan supervisord program after config changes."""
    if not command_exists(SUPERVISORCTL_COMMAND):
        raise RuntimeError("supervisorctl command was not found.")

    status = supervisorctl("status", LIBRESWAN_SERVICE_NAME, check=False)

    if "RUNNING" in status:
        supervisorctl("stop", LIBRESWAN_SERVICE_NAME, check=False)

    supervisorctl("start", LIBRESWAN_SERVICE_NAME)

    next_status = supervisorctl("status", LIBRESWAN_SERVICE_NAME, check=False)
    if "RUNNING" not in next_status:
        raise RuntimeError(f"Libreswan service did not return to RUNNING: {next_status}")


def apply_config(request: LibreswanWorkRequest) -> None:
    """Render SQLite Libreswan settings to conf/libreswan and activate them."""
    connections = load_connections()
    active_connections = render_files(connections)
    restart_libreswan_service()
    activate_connections(active_connections, request)
    logger.log("Libreswan configuration files were rendered, service was restarted, and enabled tunnels were loaded.", source=LOG_SOURCE)


def build_parser() -> argparse.ArgumentParser:
    """Build the work request executor argument parser."""
    parser = argparse.ArgumentParser(description="ArmFirewall Libreswan configuration executor.")
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
    """Execute one Libreswan work request."""
    args = build_parser().parse_args()
    request = request_from_args(args)
    validate_request(request)
    db.verify_databases(LIBRESWAN_DB_PATH, WORK_REQUEST_DB_PATH)
    apply_config(request)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd captures stderr.
        logger.error(str(exc), source=LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        sys.exit(1)
