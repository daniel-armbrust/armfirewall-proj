from __future__ import annotations

import ipaddress
import json
import re
import subprocess
import uuid
from typing import Any

from fastapi import HTTPException

from core import db
from core.iface import get_lan_primary_iface_name, get_lan_primary_ipv4_address, get_role_config
from core.system import get_hostname
from core.supervisord import supervisor_programs
from core.constants import (
    BIRD_ANY_INTERFACE,
    BIRD_BGP_SESSION_TYPES,
    BIRD_CHANNEL_FAMILIES,
    BIRD_CONFIG_PATH,
    BIRD_DB_PATH,
    BIRD_DEFAULT_CHANNEL_TABLE_NAME,
    BIRD_DEFAULT_HOSTNAME,
    BIRD_DEFAULT_ROUTER_ID,
    BIRD_IMPORT_EXPORT_VALUES,
    IFACE_DB_PATH,
    POLICY_ROUTING_DB_PATH,
    WORK_REQUEST_DB_PATH,
)

from web.services.api import service_installed, service_status_by_name


def bird_service_installed() -> bool:
    """Return whether the BIRD routing daemon is installed."""
    return service_installed("bird")


def bird_version() -> str:
    """Return the installed BIRD daemon version."""
    for command in (["bird", "--version"], ["/usr/sbin/bird", "--version"]):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
        except (OSError, subprocess.SubprocessError):
            continue

        output = (result.stdout or result.stderr or "").strip()
        
        if output:
            first_line = output.splitlines()[0]
            match = re.search(r"(\d+(?:\.\d+)+)", first_line)
    
            return match.group(1) if match else first_line
    
    return "-"


def bird_status() -> dict[str, Any]:
    """Return BIRD service status, preferring live supervisord state."""
    try:
        status = service_status_by_name("bird")
    except ValueError:
        return {
            "name": "bird",
            "display_name": "BIRD Routing Daemon",
            "installed": False,
            "state": "NOT INSTALLED",
            "pid": "-",
            "uptime": "-",
            "details": "Missing from service catalog.",
        }

    try:
        live = next((row for row in supervisor_programs() if row.get("name") == "bird"), None)
    except Exception:
        live = None

    if live is not None:
        status |= {
            "installed": True,
            "state": str(live.get("state") or status.get("state") or "UNKNOWN"),
            "pid": str(live.get("pid") or "-"),
            "uptime": str(live.get("uptime") or "-"),
            "details": str(live.get("details") or "-"),
        }

    return status


def int_setting(value: Any, *, default: int, minimum: int, maximum: int, field: str) -> int:
    """Normalize one bounded integer setting."""
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer.") from exc
    
    if parsed < minimum or parsed > maximum:
        raise HTTPException(status_code=400, detail=f"{field} must be between {minimum} and {maximum}.")
    
    return parsed


def bool_setting(value: Any) -> bool:
    """Normalize a boolean-ish payload field."""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def import_export_setting(value: Any, *, field: str, default: str) -> str:
    """Normalize one BIRD import/export policy value."""
    text = str(value if value not in (None, "") else default).strip().lower()
    
    if text not in BIRD_IMPORT_EXPORT_VALUES:
        raise HTTPException(status_code=400, detail=f"{field} must be all or none.")
    
    return text


def channel_family_setting(value: Any) -> str:
    """Normalize one BIRD channel address family."""
    family = str(value or "ipv4").strip().lower()
    
    if family not in BIRD_CHANNEL_FAMILIES:
        raise HTTPException(status_code=400, detail="channel family must be ipv4, ipv6 or ipv4/ipv6.")
    
    return family


def optional_text(value: Any) -> str | None:
    """Return a stripped optional text value."""
    text = str(value or "").strip()
    
    return text or None


def iface_name_setting(value: Any) -> str:
    """Normalize an optional BIRD interface selector."""
    text = optional_text(value)
    
    if text is None:
        return ""
    
    if text.lower() == "any" or text == BIRD_ANY_INTERFACE:
        return BIRD_ANY_INTERFACE
    
    return text


def required_text(value: Any, *, field: str) -> str:
    """Return a stripped required text value."""
    text = optional_text(value)
    
    if text is None:
        raise HTTPException(status_code=400, detail=f"{field} is required.")
    
    return text


def router_id_setting(value: Any) -> str:
    """Normalize and validate the BIRD router id."""
    text = str(value or BIRD_DEFAULT_ROUTER_ID).strip()
    
    try:
        ipaddress.IPv4Address(text)
    except ipaddress.AddressValueError as exc:
        raise HTTPException(status_code=400, detail="router_id must be an IPv4 address.") from exc
    
    return text


def hostname_setting(value: Any) -> str:
    """Normalize and validate the BIRD hostname."""
    text = str(value or BIRD_DEFAULT_HOSTNAME).strip()
    
    if len(text) > 253:
        raise HTTPException(status_code=400, detail="hostname must be 253 characters or fewer.")
    
    labels = text.rstrip(".").split(".")
    label_pattern = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
    
    if not labels or any(not label_pattern.match(label) for label in labels):
        raise HTTPException(status_code=400, detail="hostname must be a valid hostname.")
    
    return text


def ip_address_setting(value: Any, *, field: str) -> str:
    """Normalize and validate an IP address field."""
    text = required_text(value, field=field)
    
    try:
        ipaddress.ip_address(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an IP address.") from exc
    
    return text


def choice_setting(value: Any, *, field: str, choices: set[str], default: str) -> str:
    """Normalize a constrained text choice."""
    text = str(value if value not in (None, "") else default).strip().lower()
    
    if text not in choices:
        allowed = ", ".join(sorted(choices))
        raise HTTPException(status_code=400, detail=f"{field} must be one of: {allowed}.")
    
    return text


def default_hostname() -> str:
    """Return a stable default hostname for BIRD global settings."""
    try:
        return hostname_setting(get_hostname())
    except HTTPException:
        return BIRD_DEFAULT_HOSTNAME


def default_router_id() -> str:
    """Return the LAN IPv4 address as the default BIRD router id."""
    try:
        lan_ipv4 = get_lan_primary_ipv4_address()
        if lan_ipv4:
            return router_id_setting(lan_ipv4)
    except HTTPException:
        pass
   
    return BIRD_DEFAULT_ROUTER_ID


def parse_router_settings(text: str) -> dict[str, Any]:
    """Extract global router settings from an existing BIRD config."""
    settings = {"router_id": default_router_id(), "hostname": default_hostname(), "log_syslog": True}
    router_match = re.search(r"^\s*router\s+id\s+([0-9.]+)\s*;", text, re.MULTILINE)
    hostname_match = re.search(r'^\s*hostname\s+"([^"]+)"\s*;', text, re.MULTILINE)
    log_match = re.search(r"^\s*log\s+syslog\s+(all|off)\s*;", text, re.MULTILINE)
    
    if router_match:
        settings["router_id"] = router_match.group(1)
    
    if hostname_match:
        settings["hostname"] = hostname_match.group(1)
    
    if log_match:
        settings["log_syslog"] = log_match.group(1) == "all"
    
    return settings


def routing_tables() -> list[dict[str, Any]]:
    """Return policy routing table choices for BIRD kernel protocol."""
    try:
        with db.connection(POLICY_ROUTING_DB_PATH) as conn:
            columns = db.fetch_all_on(conn, "PRAGMA table_info(routing_tables)")
            has_pending_delete = any(column["name"] == "pending_delete" for column in columns)
            delete_filter = "AND pending_delete = 0" if has_pending_delete else ""
            
            return db.rows_to_dicts(db.fetch_all_on(
                conn,
                f"""
                SELECT id, table_id, table_name
                FROM routing_tables
                WHERE enabled = 1 {delete_filter}
                ORDER BY table_id
                """,
            ))
    except (FileNotFoundError, db.DatabaseError):
        return [
            {"id": None, "table_id": 253, "table_name": "default"},
            {"id": None, "table_id": 254, "table_name": "main"},
            {"id": None, "table_id": 255, "table_name": "local"},
        ]


def interfaces() -> list[dict[str, Any]]:
    """Return interface choices for BIRD device/direct protocols."""
    try:
        with db.connection(IFACE_DB_PATH) as conn:
            return db.rows_to_dicts(db.fetch_all_on(
                conn,
                """
                SELECT id, name, description, role
                FROM ifaces
                ORDER BY CASE role WHEN 'LAN' THEN 0 WHEN 'WAN' THEN 1 ELSE 2 END, name
                """,
            ))
    except (FileNotFoundError, db.DatabaseError):
        return []


def default_iface_name() -> str:
    """Return the default interface for BIRD device/direct protocols."""
    role_config = get_role_config()
    lan_iface = str(role_config.get("lan_iface") or "").strip()
    
    if lan_iface:
        return lan_iface
    
    primary_iface = get_lan_primary_iface_name()
    
    if primary_iface:
        return primary_iface
    
    items = interfaces()
    
    for item in items:
        name = str(item["name"] or "")
    
        if name and name != "lo" and not name.startswith("armfw"):
            return name
    
    return ""


def persisted_iface_name(value: Any) -> str:
    """Return a persisted BIRD interface or the default LAN interface."""
    iface_name = str(value or "").strip()
    
    if not iface_name or iface_name == "lo" or iface_name.startswith("armfw"):
        return default_iface_name()
    
    return iface_name


def queue_bird_apply(operation: str) -> int:
    """Queue a BIRD configuration apply work request."""
    request_uid = str(uuid.uuid4())

    payload = {
        "service_name": "bird",
        "display_name": "BIRD Routing Daemon",
        "operation": operation,
        "config_db": str(BIRD_DB_PATH),
        "config_path": str(BIRD_CONFIG_PATH),
    }

    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, priority, status, payload_json
            )
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.BIRD_CONFIG', 'apply', NULL, 70, 'queue', ?)
            """,
            (request_uid, json.dumps(payload, sort_keys=True)),
        )

        work_request_id = int(cursor.lastrowid)
        
        db.execute_on(
            conn,
            """
            INSERT INTO work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', ?)
            """,
            (work_request_id, f"Queued BIRD configuration apply: {operation}."),
        )

        return work_request_id


def latest_diagnostic_command(conn: db.Connection, command: str) -> dict[str, Any]:
    """Return the latest collected diagnostic command output."""
    row = db.fetch_one_on(
        conn,
        """
        SELECT id, command, exit_code, stdout, stderr, duration_ms, collected_at
        FROM diagnostic_command_run
        WHERE command = ?
        ORDER BY collected_at DESC, id DESC
        LIMIT 1
        """,
        (command,),
    )

    if row is None:
        return {
            "command": command,
            "last_run": None,
            "raw_output": "",
            "error_output": "",
        }
    
    return {
        "command": command,
        "last_run": {
            "id": int(row["id"]),
            "command": str(row["command"]),
            "exit_code": int(row["exit_code"]),
            "duration_ms": row["duration_ms"],
            "collected_at": str(row["collected_at"]),
        },
        "raw_output": str(row["stdout"] or ""),
        "error_output": str(row["stderr"] or ""),
    }
