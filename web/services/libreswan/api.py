from __future__ import annotations

import json
import ipaddress
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core import db
from core import ipsec
from core.constants import IFACE_DB_PATH, LIBRESWAN_DB_PATH, WORK_REQUEST_DB_PATH
from web.services.api import service_installed
from web.services.libreswan.constants import (
    AUTO_VALUES,
    CONNECTION_FIELDS,
    ENCAPSULATION_VALUES,
    IKEV2_VALUES,
    LIBRESWAN_LOG_FILES,
    YES_NO_VALUES,
)
from web.workrequests.api import list_work_requests


def libreswan_service_installed() -> bool:
    """Return whether the Libreswan IPsec service is installed."""
    return service_installed("libreswan")


def ensure_libreswan_schema() -> None:
    """Apply lightweight Libreswan schema compatibility fixes."""
    with db.transaction(LIBRESWAN_DB_PATH) as conn:
        db.execute_on(conn, "DROP INDEX IF EXISTS idx_libreswan_connections_left_addr")
        columns = {str(row["name"]) for row in db.execute_on(conn, "PRAGMA table_info(libreswan_connections)").fetchall()}
        if "vti_addr" not in columns:
            db.execute_on(conn, "ALTER TABLE libreswan_connections ADD COLUMN vti_addr TEXT NOT NULL DEFAULT ''")
        if "vti_mtu" not in columns:
            db.execute_on(conn, "ALTER TABLE libreswan_connections ADD COLUMN vti_mtu INTEGER NOT NULL DEFAULT 0")


def get_libreswan_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent Libreswan configuration and service control work requests."""
    return list_work_requests(
        limit=limit,
        category_names=("SERVICE_MANAGEMENT.LIBRESWAN_CONFIG", "SERVICE_MANAGEMENT.SERVICE_CONTROL"),
        service_name="libreswan",
        service_name_categories=("SERVICE_MANAGEMENT.SERVICE_CONTROL",),
    )


def normalize_limit(value: Any, *, default: int = 200, maximum: int = 1000) -> int:
    """Normalize a row limit for Libreswan API listings."""
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = default

    return max(1, min(limit, maximum))


def tail_log_file(path: Path, *, limit: int) -> list[str]:
    """Return the last log lines from one Libreswan process log file."""
    if not path.exists():
        return [f"{path} does not exist yet."]

    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 256 * 1024))
            content = handle.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return [f"Could not read {path}: {exc}"]

    lines = content.splitlines()
    return lines[-limit:] if len(lines) > limit else lines


def list_logs(limit: int = 400) -> dict[str, Any]:
    """Return Libreswan stdout and stderr merged into one chronological log view."""
    normalized_limit = normalize_limit(limit, default=400, maximum=2000)
    merged: list[tuple[float, str]] = []

    for _label, path in LIBRESWAN_LOG_FILES:
        lines = tail_log_file(path, limit=normalized_limit)
        stat = path.stat() if path.exists() else None
        mtime = float(stat.st_mtime) if stat else 0.0
        for line in lines:
            merged.append((mtime, line))

    merged.sort(key=lambda item: item[0])
    lines = [line for _, line in merged][-normalized_limit:]
    latest_mtime = max((item[0] for item in merged), default=0.0)
    summary = {
        "rows": len(lines),
        "files": len(LIBRESWAN_LOG_FILES),
        "updated_at": db.sqlite_timestamp(datetime.fromtimestamp(latest_mtime)) if latest_mtime else "-",
    }

    return {"summary": summary, "lines": lines}


def queue_libreswan_apply(
    operation: str,
    *,
    connection_id: int | None = None,
    conn_name: str | None = None,
    previous_conn_name: str | None = None,
    conn: db.Connection | None = None,
    table_prefix: str = "",
) -> int:
    """Queue Libreswan configuration rendering and activation."""
    payload = {
        "service_name": "libreswan",
        "operation": operation,
        "connection_id": connection_id,
        "conn_name": conn_name,
        "previous_conn_name": previous_conn_name,
    }

    def insert_work_request(target_conn: db.Connection, prefix: str) -> int:
        cursor = db.execute_on(
            target_conn,
            f"""
            INSERT INTO {prefix}work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, priority, status, payload_json
            )
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.LIBRESWAN_CONFIG', 'apply', ?, 70, 'queue', ?)
            """,
            (
                str(uuid.uuid4()),
                connection_id,
                json.dumps(payload, sort_keys=True),
            ),
        )
        work_request_id = int(cursor.lastrowid)
        db.execute_on(
            target_conn,
            f"""
            INSERT INTO {prefix}work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', ?)
            """,
            (work_request_id, f"Queued Libreswan configuration apply: {operation}."),
        )

        return work_request_id

    if conn is not None:
        return insert_work_request(conn, table_prefix)

    with db.transaction(WORK_REQUEST_DB_PATH) as work_conn:
        work_request_id = insert_work_request(work_conn, "")

    return work_request_id


def text_value(payload: dict[str, Any], name: str, default: str = "") -> str:
    """Return one stripped text payload value."""
    value = payload.get(name, default)
    return str(value if value is not None else default).strip()


def enabled_value(payload: dict[str, Any], default: int = 1) -> int:
    """Return normalized enabled flag."""
    value = payload.get("enabled", default)

    if isinstance(value, bool):
        return 1 if value else 0
    
    return 1 if str(value).strip() in {"1", "true", "TRUE", "yes", "on"} else 0


def choice_value(payload: dict[str, Any], name: str, allowed: set[str], default: str) -> str:
    """Return a validated choice payload value."""
    value = text_value(payload, name, default)
    
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(allowed))}.")
    
    return value


def cidr_value(payload: dict[str, Any], name: str) -> str:
    """Return a validated optional IPv4 CIDR value."""
    value = text_value(payload, name)
    if not value:
        return ""

    try:
        interface = ipaddress.ip_interface(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use CIDR format, for example 169.254.10.2/30.") from exc
    if interface.version != 4:
        raise ValueError(f"{name} must be an IPv4 address and mask, for example 169.254.10.2/30.")

    return value


def mtu_value(payload: dict[str, Any], name: str) -> int:
    """Return a validated optional interface MTU value."""
    value = text_value(payload, name)
    if not value:
        return 0

    try:
        mtu = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number between 576 and 9000.") from exc

    if mtu == 0:
        return 0
    if mtu < 576 or mtu > 9000:
        raise ValueError(f"{name} must be a number between 576 and 9000.")

    return mtu


def vti_number(name: str) -> int:
    """Return the numeric suffix from a vti interface name."""
    match = re.match(r"^vti(\d+)$", str(name or ""), flags=re.IGNORECASE)
    
    return int(match.group(1)) if match else 0


def next_vti_interface(*, exclude_connection_id: int | None = None) -> str:
    """Return the next available VTI interface name."""
    used_numbers: set[int] = set()

    try:
        iface_rows = db.fetch_all(
            """
            SELECT name
            FROM ifaces
            WHERE lower(name) LIKE 'vti%'
            """,
            db_path=IFACE_DB_PATH,
        )
        used_numbers.update(number for row in iface_rows if (number := vti_number(str(row["name"]))) > 0)
    except (FileNotFoundError, db.DatabaseError):
        pass

    params: tuple[Any, ...] = ()
    where = ""

    if exclude_connection_id is not None:
        where = "WHERE id <> ?"
        params = (exclude_connection_id,)

    rows = db.fetch_all(
        f"""
        SELECT vti_interface
        FROM libreswan_connections
        {where}
        """,
        params,
        db_path=LIBRESWAN_DB_PATH,
    )
    
    used_numbers.update(number for row in rows if (number := vti_number(str(row["vti_interface"]))) > 0)

    next_number = 1
    
    while next_number in used_numbers:
        next_number += 1
    
    return f"vti{next_number}"


def mark_number(value: str) -> int:
    """Return the numeric prefix from one Libreswan mark value."""
    match = re.match(r"^(\d+)(?:/0x[0-9a-fA-F]+)?$", str(value or "").strip())

    return int(match.group(1)) if match else 0


def next_mark(*, exclude_connection_id: int | None = None) -> str:
    """Return the next available Libreswan mark value."""
    params: tuple[Any, ...] = ()
    where = ""

    if exclude_connection_id is not None:
        where = "WHERE id <> ?"
        params = (exclude_connection_id,)

    rows = db.fetch_all(
        f"""
        SELECT mark
        FROM libreswan_connections
        {where}
        """,
        params,
        db_path=LIBRESWAN_DB_PATH,
    )

    used_numbers = {number for row in rows if (number := mark_number(str(row["mark"]))) > 0}
    next_number = 5

    while next_number in used_numbers:
        next_number += 1

    return f"{next_number}/0xffffffff"


def mark_in_use(mark: str, *, exclude_connection_id: int | None = None) -> bool:
    """Return whether one Libreswan mark is already assigned."""
    params: tuple[Any, ...] = (mark,)
    where = "WHERE mark = ?"

    if exclude_connection_id is not None:
        where = "WHERE mark = ? AND id <> ?"
        params = (mark, exclude_connection_id)

    rows = db.fetch_all(
        f"""
        SELECT id
        FROM libreswan_connections
        {where}
        LIMIT 1
        """,
        params,
        db_path=LIBRESWAN_DB_PATH,
    )

    return bool(rows)


def connection_name_in_use(conn_name: str, *, exclude_connection_id: int | None = None) -> bool:
    """Return whether one Libreswan connection name is already assigned."""
    params: tuple[Any, ...] = (conn_name,)
    where = "WHERE conn_name = ?"

    if exclude_connection_id is not None:
        where = "WHERE conn_name = ? AND id <> ?"
        params = (conn_name, exclude_connection_id)

    rows = db.fetch_all(
        f"""
        SELECT id
        FROM libreswan_connections
        {where}
        LIMIT 1
        """,
        params,
        db_path=LIBRESWAN_DB_PATH,
    )

    return bool(rows)


def right_ip_in_use(address: str, *, exclude_connection_id: int | None = None) -> bool:
    """Return whether one Libreswan right endpoint IP is already assigned."""
    params: tuple[Any, ...] = (address,)
    where = "WHERE right_addr = ?"

    if exclude_connection_id is not None:
        where = "WHERE right_addr = ? AND id <> ?"
        params = (address, exclude_connection_id)

    rows = db.fetch_all(
        f"""
        SELECT id
        FROM libreswan_connections
        {where}
        LIMIT 1
        """,
        params,
        db_path=LIBRESWAN_DB_PATH,
    )

    return bool(rows)


def database_error_message(exc: db.DatabaseError) -> str:
    """Return a user-facing message for SQLite constraint errors."""
    message = str(exc)

    if "Shared secret is required" in message:
        return "Shared secret is required."
    if "libreswan_connections.conn_name" in message:
        return "Connection Name already exists."
    if "libreswan_connections.right_addr" in message:
        return "Right IP address already exists."
    if "libreswan_connections.mark" in message:
        return "Mark already exists."
    if "CHECK constraint failed" in message and "left_addr <> right_addr" in message:
        return "Left and Right IP addresses must be different."

    return f"Libreswan connection could not be saved: {message}"


def connection_payload(payload: dict[str, Any], *, connection_id: int | None = None) -> dict[str, Any]:
    """Validate and normalize a Libreswan connection payload."""
    conn_name = text_value(payload, "conn_name")
    left_addr = text_value(payload, "left_addr")
    right_addr = text_value(payload, "right_addr")
    shared_secret = text_value(payload, "shared_secret")
    mark = text_value(payload, "mark")
    vti_interface = text_value(payload, "vti_interface")
    vti_addr = cidr_value(payload, "vti_addr")
    vti_mtu = mtu_value(payload, "vti_mtu")

    if not left_addr:
        raise ValueError("Left address is required.")
    
    if not right_addr:
        raise ValueError("Right address is required.")

    if left_addr == right_addr:
        raise ValueError("Left and Right IP addresses must be different.")

    ensure_libreswan_schema()

    if right_ip_in_use(right_addr, exclude_connection_id=connection_id):
        raise ValueError("Right IP address already exists.")

    if not shared_secret:
        raise ValueError("Shared secret is required.")
    
    if not mark:
        mark = next_mark(exclude_connection_id=connection_id)
    elif mark_in_use(mark, exclude_connection_id=connection_id):
        mark = next_mark(exclude_connection_id=connection_id)
    
    if not vti_interface:
        vti_interface = next_vti_interface(exclude_connection_id=connection_id)
    
    if not conn_name:
        conn_name = f"ipsec-{vti_interface}"

    if connection_name_in_use(conn_name, exclude_connection_id=connection_id):
        raise ValueError("Connection Name already exists.")

    return {
        "conn_name": conn_name,
        "description": text_value(payload, "description"),
        "enabled": enabled_value(payload),
        "left_addr": left_addr,
        "left_id": text_value(payload, "left_id"),
        "right_addr": right_addr,
        "authby": "secret",
        "shared_secret": shared_secret,
        "leftsubnet": text_value(payload, "leftsubnet", "0.0.0.0/0") or "0.0.0.0/0",
        "rightsubnet": text_value(payload, "rightsubnet", "0.0.0.0/0") or "0.0.0.0/0",
        "auto": choice_value(payload, "auto", AUTO_VALUES, "start"),
        "mark": mark,
        "vti_interface": vti_interface,
        "vti_addr": vti_addr,
        "vti_mtu": vti_mtu,
        "vti_routing": choice_value(payload, "vti_routing", YES_NO_VALUES, "no"),
        "ikev2": choice_value(payload, "ikev2", IKEV2_VALUES, "no"),
        "ike": text_value(payload, "ike", "aes_cbc256-sha2_384;modp1536") or "aes_cbc256-sha2_384;modp1536",
        "phase2alg": text_value(payload, "phase2alg", "aes_gcm256;modp1536") or "aes_gcm256;modp1536",
        "encapsulation": choice_value(payload, "encapsulation", ENCAPSULATION_VALUES, "yes"),
        "ikelifetime": text_value(payload, "ikelifetime", "28800s") or "28800s",
        "salifetime": text_value(payload, "salifetime", "3600s") or "3600s",
    }


def list_connections() -> dict[str, Any]:
    """Return Libreswan connection inventory."""
    ensure_libreswan_schema()

    rows = db.fetch_all(
        """
        SELECT *
        FROM libreswan_connections
        ORDER BY conn_name
        """,
        db_path=LIBRESWAN_DB_PATH,
    )

    enabled = sum(1 for row in rows if int(row["enabled"]) == 1)
    established_names = ipsec.established_connection_names()
    for row in rows:
        row["ipsec_status"] = "up" if str(row["conn_name"]) in established_names else "down"
    
    return {
        "summary": {
            "connections": len(rows),
            "enabled": enabled,
            "disabled": len(rows) - enabled,
            "updated_at": db.sqlite_timestamp(),
        },
        "connections": rows,
    }


def create_connection(payload: dict[str, Any]) -> dict[str, Any]:
    """Create one Libreswan connection."""
    item = connection_payload(payload)

    try:
        with db.transaction(LIBRESWAN_DB_PATH) as conn:
            db.execute_on(conn, "ATTACH DATABASE ? AS workreq", (str(WORK_REQUEST_DB_PATH),))
            cursor = db.execute_on(
                conn,
                """
                INSERT INTO libreswan_connections (
                    conn_name, description, enabled, left_addr, left_id, right_addr,
                    authby, shared_secret, leftsubnet, rightsubnet, auto, mark, vti_interface,
                    vti_addr, vti_mtu, vti_routing, ikev2, ike, phase2alg, encapsulation,
                    ikelifetime, salifetime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(item[name] for name in CONNECTION_FIELDS),
            )
            connection_id = int(cursor.lastrowid)
            work_request_id = queue_libreswan_apply(
                "create",
                connection_id=connection_id,
                conn_name=item["conn_name"],
                conn=conn,
                table_prefix="workreq.",
            )
    except db.DatabaseError as exc:
        raise ValueError(database_error_message(exc)) from exc

    return {"id": connection_id, "status": "created", "work_request_id": work_request_id}


def update_connection(connection_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update one Libreswan connection."""
    previous = db.fetch_one(
        """
        SELECT conn_name
        FROM libreswan_connections
        WHERE id = ?
        """,
        (connection_id,),
        db_path=LIBRESWAN_DB_PATH,
    )
    if previous is None:
        raise ValueError("Libreswan connection was not found.")

    item = connection_payload(payload, connection_id=connection_id)

    try:
        rowcount = db.execute(
            """
            UPDATE libreswan_connections
               SET conn_name = ?,
                   description = ?,
                   enabled = ?,
                   left_addr = ?,
                   left_id = ?,
                   right_addr = ?,
                   authby = ?,
                   shared_secret = ?,
                   leftsubnet = ?,
                   rightsubnet = ?,
                   auto = ?,
                   mark = ?,
                   vti_interface = ?,
                   vti_addr = ?,
                   vti_mtu = ?,
                   vti_routing = ?,
                   ikev2 = ?,
                   ike = ?,
                   phase2alg = ?,
                   encapsulation = ?,
                   ikelifetime = ?,
                   salifetime = ?,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (*tuple(item[name] for name in CONNECTION_FIELDS), connection_id),
            db_path=LIBRESWAN_DB_PATH,
        )
    except db.DatabaseError as exc:
        raise ValueError(database_error_message(exc)) from exc
    if rowcount == 0:
        raise ValueError("Libreswan connection was not found.")

    work_request_id = queue_libreswan_apply(
        "update",
        connection_id=connection_id,
        conn_name=item["conn_name"],
        previous_conn_name=str(previous["conn_name"]),
    )

    return {"id": connection_id, "status": "updated", "work_request_id": work_request_id}


def set_connection_enabled(connection_id: int, enabled: bool) -> dict[str, Any]:
    """Enable or disable one Libreswan connection."""
    previous = db.fetch_one(
        """
        SELECT conn_name
        FROM libreswan_connections
        WHERE id = ?
        """,
        (connection_id,),
        db_path=LIBRESWAN_DB_PATH,
    )
    if previous is None:
        raise ValueError("Libreswan connection was not found.")

    rowcount = db.execute(
        """
        UPDATE libreswan_connections
           SET enabled = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (1 if enabled else 0, connection_id),
        db_path=LIBRESWAN_DB_PATH,
    )

    if rowcount == 0:
        raise ValueError("Libreswan connection was not found.")

    work_request_id = queue_libreswan_apply(
        "enable" if enabled else "disable",
        connection_id=connection_id,
        conn_name=str(previous["conn_name"]),
    )

    return {"id": connection_id, "enabled": 1 if enabled else 0, "work_request_id": work_request_id}


def delete_connection(connection_id: int) -> dict[str, Any]:
    """Delete one Libreswan connection and queue its configuration apply."""
    with db.transaction(LIBRESWAN_DB_PATH) as conn:
        db.execute_on(conn, "ATTACH DATABASE ? AS workreq", (str(WORK_REQUEST_DB_PATH),))
        previous = db.fetch_one_on(
            conn,
            """
            SELECT conn_name
            FROM libreswan_connections
            WHERE id = ?
            """,
            (connection_id,),
        )
        if previous is None:
            raise ValueError("Libreswan connection was not found.")

        cursor = db.execute_on(conn, "DELETE FROM libreswan_connections WHERE id = ?", (connection_id,))
        if cursor.rowcount == 0:
            raise ValueError("Libreswan connection was not found.")

        work_request_id = queue_libreswan_apply(
            "delete",
            connection_id=connection_id,
            previous_conn_name=str(previous["conn_name"]),
            conn=conn,
            table_prefix="workreq.",
        )

    return {"id": connection_id, "status": "deleted", "work_request_id": work_request_id}
