from __future__ import annotations

from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from core.constants import WORK_REQUESTS_DEFAULT_PAGE_SIZE, WORK_REQUESTS_MAX_PAGE_SIZE
from web.workrequests import api as workrequests_api
from web.workrequests import views as workrequests_views


router = APIRouter()


@router.get("/armfirewall/work-requests", response_class=HTMLResponse)
def work_requests_page(request: Request) -> HTMLResponse:
    """Render the global ArmFirewall Work Requests page."""
    return workrequests_views.render_work_requests(request)


@router.get("/api/work-requests")
def api_work_requests(
    limit: Annotated[int, Query(ge=1, le=WORK_REQUESTS_MAX_PAGE_SIZE)] = WORK_REQUESTS_DEFAULT_PAGE_SIZE,
    page: Annotated[int, Query(ge=1)] = 1,
    category: Annotated[Optional[List[str]], Query()] = None,
    category_like: Optional[str] = None,
    service_name: Optional[str] = None,
    include_payload: bool = False,
) -> dict[str, Any]:
    """Return ArmFirewall work requests using shared filters."""
    return workrequests_api.get_work_requests(
        limit=limit,
        page=page,
        categories=tuple(category or ()),
        category_like=category_like,
        service_name=service_name,
        include_payload=include_payload,
    )


@router.post("/api/work-requests")
def api_queue_work_request(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Queue one generic ArmFirewall work request."""
    try:
        work_request_id = workrequests_api.queue_work_request(
            action=str(payload.get("action", "")),
            payload=dict(payload.get("payload") or {}),
            category_name=str(payload.get("category_name", "")),
            source=str(payload.get("source", "gui")),
            priority=int(payload.get("priority", 80)),
            target_rule_id=payload.get("target_rule_id"),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "queue",
        "work_request_id": work_request_id,
    }


@router.get("/api/work-requests/services")
def api_service_work_requests(limit: Annotated[int, Query(ge=1, le=500)] = 50) -> dict[str, Any]:
    """Return service management work requests."""
    return workrequests_api.get_service_work_requests(limit=limit)


@router.post("/api/work-requests/services")
def api_queue_service_work_request(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Queue one service management work request."""
    try:
        action = str(payload.get("action", ""))
        category_name = str(payload.get("category_name", "SERVICE_MANAGEMENT.OPTIONAL_SERVICES"))
        work_request_id = workrequests_api.queue_service_work_request(
            action,
            dict(payload.get("payload") or {}),
            category_name=category_name,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "queue",
        "work_request_id": work_request_id,
    }
