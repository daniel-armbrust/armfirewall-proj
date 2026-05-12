#!/usr/bin/env python3
"""Persistent Link Failover daemon for ArmFirewall."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core import db
from core.constants import DB_DIR
from core import log as logger


LINKFAILOVER_DB_PATH = DB_DIR / "linkfailover.db"
LOG_SOURCE = "linkfailover.py"
PING_TIME_RE = re.compile(r"time[=<]([0-9.]+)\s*ms")


@dataclass(frozen=True)
class Link:
    """Represent one configured failover link."""

    id: int
    iface: str
    priority: int


@dataclass(frozen=True)
class CheckResult:
    """Represent the outcome of one link health check."""

    link: Link
    healthy: bool
    latency_ms: float | None
    error: str | None


def verify_database() -> None:
    """Verify that linkfailover.db can be opened."""
    with db.connection(LINKFAILOVER_DB_PATH) as conn:
        db.fetch_one_on(conn, "SELECT 1")


def run_command(command: list[str], timeout: int = 10, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run one operating system command and capture text output."""
    return subprocess.run(command, check=check, capture_output=True, text=True, timeout=timeout)


def fetch_settings(conn: db.Connection) -> dict[str, Any]:
    """Return singleton Link Failover settings."""
    row = db.fetch_one_on(
        conn,
        """
        SELECT id, target, timeout_seconds, attempts, interval_seconds,
               max_latency_ms, check_interval_seconds, current_iface
        FROM linkfailover_settings
        WHERE id = 1
        """,
    )
    if row is None:
        raise RuntimeError("linkfailover_settings row id=1 was not found.")
    return db.row_to_dict(row)


def fetch_links(conn: db.Connection) -> list[Link]:
    """Return configured links ordered by priority."""
    rows = db.fetch_all_on(
        conn,
        """
        SELECT id, iface, priority
        FROM linkfailover_links
        ORDER BY priority ASC, id ASC
        """,
    )
    return [
        Link(
            id=int(row["id"]),
            iface=str(row["iface"]),
            priority=int(row["priority"]),
        )
        for row in rows
    ]


def parse_latency(output: str) -> float | None:
    """Extract ping latency in milliseconds from command output."""
    match = PING_TIME_RE.search(output)
    if not match:
        return None
    return float(match.group(1))


def ping_once(link: Link, settings: dict[str, Any]) -> tuple[bool, float | None, str | None]:
    """Run one ping probe for a link."""
    timeout_seconds = int(settings["timeout_seconds"])
    command = [
        "ping",
        "-I",
        link.iface,
        "-c",
        "1",
        "-W",
        str(timeout_seconds),
        str(settings["target"]),
    ]
    try:
        completed = run_command(command, timeout=timeout_seconds + 3)
    except Exception as exc:  # noqa: BLE001 - probe failures are health results.
        return False, None, str(exc)

    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
    latency = parse_latency(output)
    if completed.returncode != 0:
        return False, latency, output or f"ping exited with status {completed.returncode}"
    if latency is None:
        return False, None, output or "ping completed without latency output"
    max_latency_ms = settings.get("max_latency_ms")
    if max_latency_ms is not None and latency > float(max_latency_ms):
        return False, latency, f"latency {latency:.3f} ms exceeds max {float(max_latency_ms):.3f} ms"
    return True, latency, None


def check_link(link: Link, settings: dict[str, Any]) -> CheckResult:
    """Check one link with configured attempts and interval."""
    last_latency: float | None = None
    last_error: str | None = None
    attempts = int(settings["attempts"])
    interval_seconds = int(settings["interval_seconds"])
    for attempt in range(1, attempts + 1):
        healthy, latency, error = ping_once(link, settings)
        last_latency = latency
        last_error = error
        if healthy:
            return CheckResult(link=link, healthy=True, latency_ms=latency, error=None)
        if attempt < attempts and interval_seconds > 0:
            time.sleep(interval_seconds)
    return CheckResult(link=link, healthy=False, latency_ms=last_latency, error=last_error or "ping failed")


def check_links(links: list[Link], settings: dict[str, Any]) -> list[CheckResult]:
    """Run all link checks concurrently."""
    results: list[CheckResult] = []
    with ThreadPoolExecutor(max_workers=len(links)) as executor:
        future_map = {executor.submit(check_link, link, settings): link for link in links}
        for future in as_completed(future_map):
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - one link must not break all checks.
                link = future_map[future]
                results.append(CheckResult(link=link, healthy=False, latency_ms=None, error=str(exc)))
    return sorted(results, key=lambda item: (item.link.priority, item.link.id))


def record_event(
    conn: db.Connection,
    event_type: str,
    message: str,
    *,
    link_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist one Link Failover daemon event."""
    db.execute_on(
        conn,
        """
        INSERT INTO linkfailover_events (link_id, event_type, message, details_json)
        VALUES (?, ?, ?, ?)
        """,
        (link_id, event_type, message, json.dumps(details or {}, sort_keys=True)),
    )


def update_result(conn: db.Connection, result: CheckResult) -> None:
    """Persist the latest health check result for one link."""
    status = "healthy" if result.healthy else "failed"
    db.execute_on(
        conn,
        """
        UPDATE linkfailover_links
        SET status = ?,
            last_latency_ms = ?,
            last_error = ?,
            last_checked_at = CURRENT_TIMESTAMP,
            success_count = success_count + ?,
            fail_count = fail_count + ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            status,
            result.latency_ms,
            result.error,
            1 if result.healthy else 0,
            0 if result.healthy else 1,
            result.link.id,
        ),
    )


def record_check_summary(conn: db.Connection, results: list[CheckResult], settings: dict[str, Any]) -> None:
    """Persist one summary event for a completed health-check cycle."""
    healthy = [result.link.iface for result in results if result.healthy]
    failed = [result.link.iface for result in results if not result.healthy]
    message = f"Checked {len(results)} links against {settings['target']}: healthy={len(healthy)}, failed={len(failed)}."
    record_event(
        conn,
        "check",
        message,
        details={
            "target": settings["target"],
            "healthy": healthy,
            "failed": failed,
            "latencies_ms": {
                result.link.iface: result.latency_ms
                for result in results
                if result.latency_ms is not None
            },
        },
    )


def current_default_iface() -> str | None:
    """Return the interface used by the current IPv4 default route."""
    result = run_command(["ip", "-4", "route", "show", "default"], timeout=5)
    for line in result.stdout.splitlines():
        parts = line.split()
        if "dev" in parts:
            index = parts.index("dev")
            if index + 1 < len(parts):
                return parts[index + 1]
    return None


def remove_default_routes() -> None:
    """Remove all current IPv4 default routes from the main table."""
    for _ in range(20):
        result = run_command(["ip", "-4", "route", "show", "default"], timeout=5)
        line = next((item.strip() for item in result.stdout.splitlines() if item.strip()), "")
        if not line:
            return
        delete = run_command(["ip", "-4", "route", "del", "default"], timeout=5)
        if delete.returncode != 0:
            output = (delete.stderr or delete.stdout or "could not delete default route").strip()
            raise RuntimeError(output)


def apply_default_route(link: Link) -> None:
    """Replace the main IPv4 default route with the selected link."""
    remove_default_routes()
    result = run_command(["ip", "-4", "route", "add", "default", "dev", link.iface], timeout=8)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "could not add default route").strip()
        raise RuntimeError(output)


def select_healthy_link(results: list[CheckResult]) -> CheckResult | None:
    """Select the best healthy link by priority."""
    return next((result for result in results if result.healthy), None)


def process_cycle(conn: db.Connection) -> None:
    """Run one failover health-check and route decision cycle."""
    settings = fetch_settings(conn)
    links = fetch_links(conn)
    if len(links) < 2:
        message = "At least two links are required for Link Failover."
        record_event(conn, "warning", message)
        logger.warning(message, source=LOG_SOURCE)
        conn.commit()
        return

    results = check_links(links, settings)
    for result in results:
        update_result(conn, result)
    record_check_summary(conn, results, settings)

    selected = select_healthy_link(results)
    db.execute_on(conn, "UPDATE linkfailover_settings SET last_checked_at = CURRENT_TIMESTAMP WHERE id = 1")

    if selected is None:
        message = "All Link Failover checks failed; keeping current default route."
        record_event(conn, "warning", message, details={"links": [result.link.iface for result in results]})
        logger.warning(message, source=LOG_SOURCE)
        conn.commit()
        return

    current_iface = current_default_iface()
    if current_iface != selected.link.iface:
        apply_default_route(selected.link)
        message = f"Default route changed to {selected.link.iface}."
        db.execute_on(
            conn,
            """
            UPDATE linkfailover_settings
            SET current_iface = ?, last_route_change_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (selected.link.iface,),
        )
        record_event(
            conn,
            "route_change",
            message,
            link_id=selected.link.id,
            details={"previous_iface": current_iface, "target": settings["target"]},
        )
        logger.log(message, source=LOG_SOURCE)
    else:
        db.execute_on(
            conn,
            "UPDATE linkfailover_settings SET current_iface = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (selected.link.iface,),
        )

    conn.commit()


def main() -> None:
    """Run the Link Failover daemon loop forever."""
    verify_database()
    logger.log("Starting Link Failover daemon.", source=LOG_SOURCE)
    with db.connection(LINKFAILOVER_DB_PATH) as conn:
        while True:
            try:
                settings = fetch_settings(conn)
                process_cycle(conn)
                sleep_seconds = int(settings.get("check_interval_seconds") or 10)
            except Exception as exc:  # noqa: BLE001 - daemon must keep trying after transient failures.
                conn.rollback()
                logger.error(f"Link Failover cycle failed: {exc}", source=LOG_SOURCE)
                sleep_seconds = 10
            time.sleep(max(1, sleep_seconds))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.log("Stopping Link Failover daemon.", source=LOG_SOURCE)
        sys.exit(0)
