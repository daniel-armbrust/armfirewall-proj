"""HTTP routes for ADAM text-classification results and artifacts."""

from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import FileResponse

from core.constants import (
    ADAM_WORK_REQUEST_CATEGORY,
    ADAM_WORK_REQUEST_DELETE_ACTION,
)
from web.adam import text_classification
from web.workrequests import api as workrequests_api


def api_text_classification(dataset_category: str | None = None) -> dict[str, object]:
    """Return active shared-model details, optionally for one dataset category."""
    try:
        return {
            "training": text_classification.active_training(
                dataset_category=dataset_category
            )
        }
    except text_classification.TextClassificationStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def api_delete_text_classification(training_uid: str) -> dict[str, object]:
    """Queue deletion of the active model and its training artifacts."""
    try:
        active_training = text_classification.active_training()
    except text_classification.TextClassificationStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if active_training is None:
        raise HTTPException(
            status_code=404,
            detail="No trained text classification model is available.",
        )
    if active_training["training_uid"] != training_uid:
        raise HTTPException(
            status_code=409,
            detail="The active text classification model has changed.",
        )

    request_uid = str(uuid4())
    
    try:
        work_request_id = workrequests_api.queue_work_request(
            action=ADAM_WORK_REQUEST_DELETE_ACTION,
            category_name=ADAM_WORK_REQUEST_CATEGORY,
            source="gui",
            priority=70,
            request_uid=request_uid,
            allowed_actions=(ADAM_WORK_REQUEST_DELETE_ACTION,),
            allowed_categories=(ADAM_WORK_REQUEST_CATEGORY,),
            event_message="Queued ADAM text classifier artifact deletion.",
            payload={"training_uid": training_uid},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="The deletion work request could not be queued.",
        ) from exc

    return {
        "message": "Deletion work request queued successfully.",
        "status": "queue",
        "work_request_id": work_request_id,
        "request_uid": request_uid,
    }


def api_text_classification_chart(
    training_uid: str,
    dataset_category: str | None = None,
) -> FileResponse:
    """Return the shared-model evaluation chart for all data or one category."""
    try:
        chart_path = text_classification.evaluation_chart(
            training_uid,
            dataset_category=dataset_category,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except text_classification.TextClassificationStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FileResponse(
        chart_path,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


__all__ = [
    "api_delete_text_classification",
    "api_text_classification",
    "api_text_classification_chart",
]
