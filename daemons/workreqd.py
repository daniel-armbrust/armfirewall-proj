#!/usr/bin/env python3
"""Persistent daemon that dispatches queued work requests."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import db
from core.constants import DB_DIR, ROOT_DIR
from core import log as logger

WORK_REQUEST_DB_PATH = DB_DIR / "work-requests.db"
CHECK_INTERVAL_SECONDS = int(os.environ.get("ARMFIREWALL_ARMFWORKREQD_INTERVAL", "5"))
BATCH_SIZE = int(os.environ.get("ARMFIREWALL_ARMFWORKREQD_BATCH_SIZE", "10"))
ACTION_TIMEOUT_SECONDS = int(os.environ.get("ARMFIREWALL_ARMFWORKREQD_ACTION_TIMEOUT", "300"))
LOG_SOURCE = "workreqd.py"


def connect() -> db.Connection:
    """Open a configured work request SQLite connection."""
    return db.connect(WORK_REQUEST_DB_PATH)


def verify_work_request_database() -> None:
    """Verify that the work request database can be opened."""
    with connect() as conn:
        db.fetch_one_on(conn, "SELECT 1")


def add_event(conn: db.Connection, request_id: int, event_type: str, message: str | None = None) -> None:
    """Append a state event for one work request."""
    db.execute_on(
        conn,
        """
        INSERT INTO work_request_events (work_request_id, event_type, message)
        VALUES (?, ?, ?)
        """,
        (request_id, event_type, message),
    )


def set_status(
    conn: db.Connection,
    request_id: int,
    status: str,
    *,
    error_message: str | None = None,
) -> None:
    """Update one work request status and add a matching event."""
    db.execute_on(
        conn,
        """
        UPDATE work_requests
        SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, error_message, request_id),
    )
    add_event(conn, request_id, status, error_message)


def queued_requests(conn: db.Connection) -> list[Any]:
    """Return queued work requests in execution order."""
    return db.execute_on(
        conn,
        """
        SELECT
            wr.id,
            wr.request_uid,
            wr.category_name,
            wr.action_name,
            wr.target_rule_id,
            wr.payload_json,
            wc.category,
            wc.family,
            wc.target_name,
            wh.script_name
        FROM work_requests wr
        JOIN work_request_categories wc ON wc.name = wr.category_name
        JOIN work_request_handlers wh ON wh.category = wc.category
        WHERE wr.status = 'queue'
          AND wh.enabled = 1
        ORDER BY wr.priority ASC, wr.created_at ASC, wr.id ASC
        LIMIT ?
        """,
        (BATCH_SIZE,),
    ).fetchall()


def command_for_request(request: Any) -> list[str]:
    """Build the action command for a work request."""
    if str(request["category_name"]) == "SERVICE_MANAGEMENT.DNSMASQ_CONFIG":
        command = [sys.executable, "-m", "daemons.dnsmasq.dnsmasq"]
    else:
        script_name = str(request["script_name"])

        if "/" in script_name or ".." in script_name or not script_name.endswith(".py"):
            raise RuntimeError(f"Invalid action script name configured: {script_name}")

        script_path = ROOT_DIR / "daemons" / script_name

        if not script_path.exists():
            raise FileNotFoundError(f"Action script not found: {script_path}")
        command = [sys.executable, str(script_path)]

    return [
        *command,
        "--work-request-id",
        str(request["id"]),
        "--request-uid",
        str(request["request_uid"]),
        "--category-name",
        str(request["category_name"]),
        "--category",
        str(request["category"]),
        "--family",
        str(request["family"]),
        "--target-name",
        str(request["target_name"]),
        "--action-name",
        str(request["action_name"]),
        "--target-rule-id",
        "" if request["target_rule_id"] is None else str(request["target_rule_id"]),
        "--payload-json",
        str(request["payload_json"]),
    ]


def process_request(conn: db.Connection, request: Any) -> None:
    """Execute one queued work request and persist the final dispatch result."""
    request_id = int(request["id"])

    try:
        set_status(conn, request_id, "running")
        conn.commit()

        completed = subprocess.run(
            command_for_request(request),
            check=False,
            text=True,
            capture_output=True,
            timeout=ACTION_TIMEOUT_SECONDS,
        )

        if completed.returncode == 0:
            set_status(conn, request_id, "success")
            conn.commit()
            logger.log(f"Work request {request_id} executor returned success.", source=LOG_SOURCE)
            return

        message = (
            completed.stderr
            or completed.stdout
            or f"Action script failed with exit status {completed.returncode}."
        ).strip()

        set_status(conn, request_id, "failed", error_message=message)
        conn.commit()

        logger.error(f"Work request {request_id} failed: {message}", source=LOG_SOURCE)
    except Exception as exc:  # noqa: BLE001 - daemon must record failures.
        conn.rollback()
        with conn:
            set_status(conn, request_id, "failed", error_message=str(exc))
        logger.error(f"Work request {request_id} failed: {exc}", source=LOG_SOURCE)


def process_once(conn: db.Connection) -> int:
    """Process one batch of queued work requests."""
    requests = queued_requests(conn)

    for request in requests:
        process_request(conn, request)
        
    return len(requests)


def main() -> None:
    """Run the work request dispatcher loop forever."""
    verify_work_request_database()
    logger.log(f"Starting work request daemon with {CHECK_INTERVAL_SECONDS}s interval.", source=LOG_SOURCE)

    with connect() as conn:
        while True:
            processed = process_once(conn)
            if processed:
                logger.log(f"Processed {processed} queued work request(s).", source=LOG_SOURCE)
            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.log("Stopping work request daemon.", source=LOG_SOURCE)
        sys.exit(0)
