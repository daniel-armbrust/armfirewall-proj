from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

from core import db
from core.constants import WORK_REQUEST_DB_PATH
from web.utils import safe_decode_payload, summarize_statuses
from web.workrequests.constants import SERVICE_WORK_REQUEST_ACTIONS, SERVICE_WORK_REQUEST_CATEGORIES, WORK_REQUEST_COLUMNS


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

    return {"summary": summarize_statuses(rows, ("queue", "running", "success", "failed")), "requests": rows}


def get_work_requests(
    *,
    limit: int = 50,
    categories: Sequence[str] | None = None,
    category_like: str | None = None,
    service_name: str | None = None,
    include_payload: bool = False,
) -> dict[str, Any]:
    """Return ArmFirewall work requests for Web API consumers."""
    return list_work_requests(
        limit=limit,
        category_names=tuple(categories or ()),
        category_like=category_like,
        service_name=service_name,
        include_payload=include_payload,
        include_payload_service_fields=True,
    )


def queue_work_request(
    *,
    action: str,
    payload: dict[str, Any],
    category_name: str,
    source: str = "gui",
    priority: int = 80,
    target_rule_id: int | None = None,
    allowed_actions: Sequence[str] | None = None,
    allowed_categories: Sequence[str] | None = None,
    event_message: str | None = None,
) -> int:
    """Insert one work request and its queue event."""
    if allowed_actions is not None and action not in set(allowed_actions):
        raise ValueError("Unsupported work request action.")

    if allowed_categories is not None and category_name not in set(allowed_categories):
        raise ValueError("Unsupported work request category.")

    request_uid = str(uuid.uuid4())
    rendered_payload = json.dumps(payload, sort_keys=True)

    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, priority, status, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, 'queue', ?)
            """,
            (request_uid, source, category_name, action, target_rule_id, priority, rendered_payload),
        )

        work_request_id = int(cursor.lastrowid)
        
        db.execute_on(
            conn,
            """
            INSERT INTO work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', ?)
            """,
            (work_request_id, event_message or f"Queued {category_name} {action}."),
        )
        
        return work_request_id


def get_service_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent ArmFirewall service management work requests."""
    return get_work_requests(
        limit=limit,
        categories=tuple(SERVICE_WORK_REQUEST_CATEGORIES),
    )


def queue_service_work_request(
    action: str,
    payload: dict[str, Any],
    *,
    category_name: str = "SERVICE_MANAGEMENT.OPTIONAL_SERVICES",
) -> int:
    """Queue a service management work request and return its id."""
    return queue_work_request(
        action=action,
        payload=payload,
        category_name=category_name,
        allowed_actions=SERVICE_WORK_REQUEST_ACTIONS,
        allowed_categories=SERVICE_WORK_REQUEST_CATEGORIES,
        event_message=f"Queued service {action}: {payload.get('service_name')}",
    )
