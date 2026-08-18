"""DNSMasq application services exposed to the web layer."""
from __future__ import annotations
import json
import re
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from core import db
from core.constants import ADGUARD_HOME_SERVICE_NAME, DNSMASQ_CONF_PATH, DNSMASQ_DB_PATH, DNSMASQ_LEASES_PATH, DNSMASQ_MAC_ADDRESS_PATTERN, WORK_REQUEST_DB_PATH
from web.services.api import service_status_by_name
from web.workrequests.api import list_work_requests
from .configuration import default_config, parse_dnsmasq_config, read_config_lines, render_config, validate_dnsmasq_syntax
from .interfaces import list_interfaces
from .repository import load_config_from_db, save_config_to_db, ensure_dnsmasq_schema
from .validation import normalize_config, validate_optional_ipv4
MAC_ADDRESS_RE = re.compile(DNSMASQ_MAC_ADDRESS_PATTERN)

def dnsmasq_version() -> str:
    """Return the installed dnsmasq version when available."""
    dnsmasq = shutil.which("dnsmasq")
    if not dnsmasq:
        return "not installed"
    try:
        result = subprocess.run(
            [dnsmasq, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    output = (result.stdout or result.stderr).strip().splitlines()
    if not output:
        return "unknown"
    match = re.search(r"version\s+([^\s,]+)", output[0], re.IGNORECASE)
    return match.group(1) if match else output[0]


def dnsmasq_status() -> dict[str, Any]:
    """Return persisted dnsmasq service status."""
    status = service_status_by_name("dnsmasq")
    status["version"] = dnsmasq_version()
    return status


def get_dnsmasq_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent Dnsmasq configuration and service control work requests."""
    return list_work_requests(
        limit=limit,
        category_names=("SERVICE_MANAGEMENT.DNSMASQ_CONFIG", "SERVICE_MANAGEMENT.SERVICE_CONTROL"),
        service_name="dnsmasq",
        service_name_categories=("SERVICE_MANAGEMENT.SERVICE_CONTROL",),
    )


def get_dnsmasq_config() -> dict[str, Any]:
    """Return dnsmasq configuration, interfaces, and service state."""
    config = load_config_from_db()
    if config is None:
        config = parse_dnsmasq_config(read_config_lines())
    return {
        "config": config,
        "interfaces": list_interfaces(),
        "service": dnsmasq_status(),
        "summary": {
            "config_path": str(DNSMASQ_CONF_PATH),
            "config_db": str(DNSMASQ_DB_PATH),
            "exists": DNSMASQ_CONF_PATH.exists(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def get_dhcp_leases() -> dict[str, Any]:
    """Return the DHCP leases currently maintained by Dnsmasq."""
    config = load_config_from_db()
    if config is None:
        config = parse_dnsmasq_config(read_config_lines())
    dhcp_configured = bool(config.get("dhcp_enabled")) or any(
        item.get("dhcp_enabled") for item in config.get("interface_configs", [])
    )
    dhcp_active = dhcp_configured and str(dnsmasq_status().get("state") or "").upper() == "RUNNING"
    if not dhcp_active:
        return {
            "leases": [],
            "count": 0,
            "dhcp_active": False,
            "message": "DHCP service is not active or configured.",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    if not DNSMASQ_LEASES_PATH.is_file():
        return {
            "leases": [],
            "count": 0,
            "dhcp_active": True,
            "message": "No DHCP leases found.",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    static_leases = {
        (item["mac_address"].lower(), item["ip_address"])
        for item in config.get("static_leases", [])
    }
    leases = []
    for line in DNSMASQ_LEASES_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        try:
            expires_at = int(fields[0])
        except ValueError:
            continue
        leases.append(
            {
                "expires_at": "never" if expires_at == 0 else datetime.fromtimestamp(expires_at).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                "mac_address": fields[1],
                "ip_address": fields[2],
                "hostname": "-" if fields[3] == "*" else fields[3],
                "client_id": "-" if fields[4] == "*" else fields[4],
                "is_static": (fields[1].lower(), fields[2]) in static_leases,
            }
        )

    return {
        "leases": leases,
        "count": len(leases),
        "dhcp_active": True,
        "message": "No DHCP leases found." if not leases else "",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_static_leases() -> dict[str, Any]:
    """Return DHCP reservations configured independently of active leases."""
    config = load_config_from_db()
    if config is None:
        config = parse_dnsmasq_config(read_config_lines())
    leases = config.get("static_leases", [])
    return {"leases": leases, "count": len(leases)}


def normalize_mac_address(value: Any) -> str:
    """Validate and normalize one Ethernet MAC address."""
    mac_address = str(value or "").strip().lower()
    if not MAC_ADDRESS_RE.fullmatch(mac_address):
        raise HTTPException(status_code=400, detail="MAC address must use the format AA:BB:CC:DD:EE:FF.")
    return mac_address


def add_static_lease(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a DHCP reservation and queue configuration apply plus restart."""
    mac_address = normalize_mac_address(payload.get("mac_address"))
    ip_address = validate_optional_ipv4(payload.get("ip_address"), "IP address")
    if not ip_address:
        raise HTTPException(status_code=400, detail="IP address is required.")

    config = load_config_from_db()
    if config is None or not (
        config.get("dhcp_enabled")
        or any(item.get("dhcp_enabled") for item in config.get("interface_configs", []))
    ):
        raise HTTPException(status_code=400, detail="DHCP must be configured before adding a static address.")

    proposed_config = dict(config)
    proposed_config["static_leases"] = [
        *config.get("static_leases", []),
        {"mac_address": mac_address, "ip_address": ip_address},
    ]
    ok, message = validate_dnsmasq_syntax(render_config(proposed_config))
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    with db.transaction(DNSMASQ_DB_PATH) as conn:
        ensure_dnsmasq_schema(conn)
        try:
            db.execute_on(
                conn,
                """
                INSERT INTO dnsmasq_static_leases (mac_address, ip_address, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (mac_address, ip_address),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=400, detail="MAC address or IP address already has a static lease.") from exc

    request_uid = str(uuid.uuid4())
    payload_json = json.dumps({"config_db": str(DNSMASQ_DB_PATH), "config_path": str(DNSMASQ_CONF_PATH)}, sort_keys=True)
    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        apply_cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, priority, status, payload_json
            )
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.DNSMASQ_CONFIG', 'apply', NULL, 70, 'queue', ?)
            """,
            (request_uid, payload_json),
        )
        apply_work_request_id = int(apply_cursor.lastrowid)
        db.execute_on(
            conn,
            "INSERT INTO work_request_events (work_request_id, event_type, message) VALUES (?, 'queue', 'Queued static DHCP lease apply.')",
            (apply_work_request_id,),
        )
        restart_cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, priority, status, payload_json
            )
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.SERVICE_CONTROL', 'restart', NULL, 71, 'queue', ?)
            """,
            (str(uuid.uuid4()), json.dumps({"service_name": "dnsmasq", "display_name": "DNSMasq", "kind": "dns-dhcp"}, sort_keys=True)),
        )
        restart_work_request_id = int(restart_cursor.lastrowid)
        db.execute_on(
            conn,
            "INSERT INTO work_request_events (work_request_id, event_type, message) VALUES (?, 'queue', 'Queued DNSMasq restart for static DHCP lease.')",
            (restart_work_request_id,),
        )

    return {
        "queued": True,
        "apply_work_request_id": apply_work_request_id,
        "restart_work_request_id": restart_work_request_id,
        "message": "Static DHCP address queued for apply and DNSMasq restart.",
    }


def remove_static_lease(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove a DHCP reservation and queue configuration apply plus restart."""
    mac_address = normalize_mac_address(payload.get("mac_address"))
    ip_address = validate_optional_ipv4(payload.get("ip_address"), "IP address")
    if not ip_address:
        raise HTTPException(status_code=400, detail="IP address is required.")

    with db.transaction(DNSMASQ_DB_PATH) as conn:
        ensure_dnsmasq_schema(conn)
        cursor = db.execute_on(
            conn,
            "DELETE FROM dnsmasq_static_leases WHERE mac_address = ? AND ip_address = ?",
            (mac_address, ip_address),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status_code=404, detail="Static DHCP address was not found.")

    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        payload_json = json.dumps({"config_db": str(DNSMASQ_DB_PATH), "config_path": str(DNSMASQ_CONF_PATH)}, sort_keys=True)
        apply_cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (request_uid, source, category_name, action_name, target_rule_id, priority, status, payload_json)
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.DNSMASQ_CONFIG', 'apply', NULL, 70, 'queue', ?)
            """,
            (str(uuid.uuid4()), payload_json),
        )
        apply_work_request_id = int(apply_cursor.lastrowid)
        db.execute_on(conn, "INSERT INTO work_request_events (work_request_id, event_type, message) VALUES (?, 'queue', 'Queued static DHCP lease removal.')", (apply_work_request_id,))
        restart_cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (request_uid, source, category_name, action_name, target_rule_id, priority, status, payload_json)
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.SERVICE_CONTROL', 'restart', NULL, 71, 'queue', ?)
            """,
            (str(uuid.uuid4()), json.dumps({"service_name": "dnsmasq", "display_name": "DNSMasq", "kind": "dns-dhcp"}, sort_keys=True)),
        )
        restart_work_request_id = int(restart_cursor.lastrowid)
        db.execute_on(conn, "INSERT INTO work_request_events (work_request_id, event_type, message) VALUES (?, 'queue', 'Queued DNSMasq restart after static DHCP lease removal.')", (restart_work_request_id,))

    return {"queued": True, "apply_work_request_id": apply_work_request_id, "restart_work_request_id": restart_work_request_id}


def update_static_lease(payload: dict[str, Any]) -> dict[str, Any]:
    """Update a DHCP reservation and queue configuration apply plus restart."""
    previous_mac_address = normalize_mac_address(payload.get("previous_mac_address"))
    previous_ip_address = validate_optional_ipv4(payload.get("previous_ip_address"), "Previous IP address")
    mac_address = normalize_mac_address(payload.get("mac_address"))
    ip_address = validate_optional_ipv4(payload.get("ip_address"), "IP address")
    if not previous_ip_address or not ip_address:
        raise HTTPException(status_code=400, detail="IP address is required.")

    config = load_config_from_db()
    if config is None:
        config = parse_dnsmasq_config(read_config_lines())
    proposed_leases = []
    found = False
    for lease in config.get("static_leases", []):
        if lease["mac_address"].lower() == previous_mac_address and lease["ip_address"] == previous_ip_address:
            proposed_leases.append({"mac_address": mac_address, "ip_address": ip_address})
            found = True
        else:
            proposed_leases.append(lease)
    if not found:
        raise HTTPException(status_code=404, detail="Static DHCP address was not found.")

    proposed_config = dict(config)
    proposed_config["static_leases"] = proposed_leases
    ok, message = validate_dnsmasq_syntax(render_config(proposed_config))
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    with db.transaction(DNSMASQ_DB_PATH) as conn:
        ensure_dnsmasq_schema(conn)
        try:
            cursor = db.execute_on(
                conn,
                """
                UPDATE dnsmasq_static_leases
                SET mac_address = ?, ip_address = ?, updated_at = CURRENT_TIMESTAMP
                WHERE mac_address = ? AND ip_address = ?
                """,
                (mac_address, ip_address, previous_mac_address, previous_ip_address),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=400, detail="MAC address or IP address already has a static lease.") from exc
        if cursor.rowcount != 1:
            raise HTTPException(status_code=404, detail="Static DHCP address was not found.")

    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        payload_json = json.dumps({"config_db": str(DNSMASQ_DB_PATH), "config_path": str(DNSMASQ_CONF_PATH)}, sort_keys=True)
        apply_cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (request_uid, source, category_name, action_name, target_rule_id, priority, status, payload_json)
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.DNSMASQ_CONFIG', 'apply', NULL, 70, 'queue', ?)
            """,
            (str(uuid.uuid4()), payload_json),
        )
        apply_work_request_id = int(apply_cursor.lastrowid)
        db.execute_on(conn, "INSERT INTO work_request_events (work_request_id, event_type, message) VALUES (?, 'queue', 'Queued static DHCP address update.')", (apply_work_request_id,))
        restart_cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (request_uid, source, category_name, action_name, target_rule_id, priority, status, payload_json)
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.SERVICE_CONTROL', 'restart', NULL, 71, 'queue', ?)
            """,
            (str(uuid.uuid4()), json.dumps({"service_name": "dnsmasq", "display_name": "DNSMasq", "kind": "dns-dhcp"}, sort_keys=True)),
        )
        restart_work_request_id = int(restart_cursor.lastrowid)
        db.execute_on(conn, "INSERT INTO work_request_events (work_request_id, event_type, message) VALUES (?, 'queue', 'Queued DNSMasq restart after static DHCP address update.')", (restart_work_request_id,))

    return {"queued": True, "apply_work_request_id": apply_work_request_id, "restart_work_request_id": restart_work_request_id}


def save_dnsmasq_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist dnsmasq settings and queue an apply work request."""
    previous_config = load_config_from_db() or {}
    config = normalize_config(payload)
    if config["adguardhome_upstream_enabled"] and not previous_config.get("adguardhome_upstream_enabled"):
        adguard_state = str(service_status_by_name(ADGUARD_HOME_SERVICE_NAME).get("state") or "").upper()
        if adguard_state != "RUNNING":
            raise HTTPException(status_code=400, detail="AdGuard Home must be running before DNS filtering can be enabled.")
    config_text = render_config(config)
    ok, message = validate_dnsmasq_syntax(config_text)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    work_request_id = save_config_to_db(config)
    adguard_restart_work_request_id = None
    if config["adguardhome_upstream_enabled"]:
        with db.transaction(WORK_REQUEST_DB_PATH) as conn:
            cursor = db.execute_on(
                conn,
                """
                INSERT INTO work_requests (
                    request_uid, source, category_name, action_name,
                    target_rule_id, priority, status, payload_json
                )
                VALUES (?, 'gui', 'SERVICE_MANAGEMENT.SERVICE_CONTROL', 'restart', NULL, 69, 'queue', ?)
                """,
                (
                    str(uuid.uuid4()),
                    json.dumps(
                        {
                            "service_name": ADGUARD_HOME_SERVICE_NAME,
                            "display_name": "AdGuard Home",
                            "kind": "dns-filtering",
                        },
                        sort_keys=True,
                    ),
                ),
            )
            adguard_restart_work_request_id = int(cursor.lastrowid)
            db.execute_on(
                conn,
                """
                INSERT INTO work_request_events (work_request_id, event_type, message)
                VALUES (?, 'queue', 'Queued AdGuard Home restart before DNS filtering apply.')
                """,
                (adguard_restart_work_request_id,),
            )
    return {
        "saved": True,
        "queued": True,
        "work_request_id": work_request_id,
        "adguard_restart_work_request_id": adguard_restart_work_request_id,
        "message": "DNSMasq configuration queued for apply.",
        "config": config,
        "summary": {
            "config_path": str(DNSMASQ_CONF_PATH),
            "config_db": str(DNSMASQ_DB_PATH),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def test_dnsmasq_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate either posted settings or the current dnsmasq.conf."""
    if payload:
        config_text = render_config(normalize_config(payload))
    else:
        config_text = DNSMASQ_CONF_PATH.read_text(encoding="utf-8") if DNSMASQ_CONF_PATH.exists() else render_config(default_config())

    ok, message = validate_dnsmasq_syntax(config_text)
    return {"ok": ok, "message": message}
