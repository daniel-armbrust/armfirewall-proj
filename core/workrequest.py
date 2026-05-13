"""Shared helpers for ArmFirewall work request executors."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from core import db
from core.constants import WORK_REQUEST_DB_PATH


WORK_REQUEST_COLUMNS = """
    id,
    request_uid,
    status,
    source,
    category_name,
    action_name,
    target_rule_id,
    priority,
    payload_json,
    error_message,
    created_at,
    updated_at
"""


def decode_payload(payload_json: str | None) -> dict[str, Any]:
    """Decode a work request JSON payload into a dictionary."""
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Payload JSON must decode to an object.")
    return payload


def safe_decode_payload(payload_json: str | None) -> dict[str, Any]:
    """Decode a work request payload, returning an empty dict on invalid JSON."""
    try:
        return decode_payload(payload_json)
    except RuntimeError:
        return {}


def summarize_work_requests(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Return a status summary for a list of work requests."""
    summary = {"total": len(rows), "queue": 0, "running": 0, "success": 0, "failed": 0}
    for row in rows:
        status = str(row.get("status") or "")
        if status in summary:
            summary[status] += 1
    return summary


def list_work_requests(
    *,
    limit: int = 50,
    category_names: Sequence[str] | None = None,
    category_like: str | None = None,
    service_name: str | None = None,
    service_name_categories: Sequence[str] | None = None,
    include_payload: bool = False,
    include_payload_service_fields: bool = False,
) -> dict[str, Any]:
    """Return work requests filtered by category and optional payload service name."""
    normalized_limit = max(1, min(int(limit), 500))
    where: list[str] = []
    params: list[Any] = []

    if category_names:
        placeholders = ", ".join("?" for _ in category_names)
        where.append(f"category_name IN ({placeholders})")
        params.extend(category_names)

    if category_like:
        where.append("category_name LIKE ?")
        params.append(category_like)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    query = f"""
        SELECT {WORK_REQUEST_COLUMNS}
        FROM work_requests
        {where_sql}
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(normalized_limit if service_name is None else 500)

    try:
        with db.connection(WORK_REQUEST_DB_PATH) as conn:
            raw_rows = db.fetch_all_on(conn, query, params)
    except FileNotFoundError:
        raw_rows = []

    service_filter_categories = set(service_name_categories or ())
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        payload = safe_decode_payload(str(row.get("payload_json") or "{}"))
        category_name = str(row.get("category_name") or "")
        service_filter_applies = service_name is not None and (
            not service_filter_categories or category_name in service_filter_categories
        )
        if service_filter_applies and payload.get("service_name") != service_name:
            continue

        item = dict(row)
        if include_payload_service_fields:
            item["service_name"] = payload.get("service_name", "-")
            item["display_name"] = payload.get("display_name", item["service_name"])

        if include_payload:
            item["payload"] = payload
        item.pop("payload_json", None)

        rows.append(item)
        if len(rows) >= normalized_limit:
            break

    return {"summary": summarize_work_requests(rows), "requests": rows}
