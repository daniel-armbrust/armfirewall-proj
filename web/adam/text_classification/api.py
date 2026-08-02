"""HTTP handlers for ADAM text-classification training and results."""

from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse

from core.constants import (
    ADAM_DATASET_MAX_BYTES,
    ADAM_WORK_REQUEST_CATEGORY,
    ADAM_WORK_REQUEST_DELETE_ACTION,
)
from web.adam.datasets import service as datasets_service
from web.workrequests import api as workrequests_api

from .errors import TextClassificationStorageError
from . import service


async def api_queue_training(
    training_dataset: UploadFile,
    testing_dataset: UploadFile,
    dataset_category: str,
) -> dict[str, object]:
    """Validate, store, and queue training for one selected dataset pair."""
    training_content = await training_dataset.read(ADAM_DATASET_MAX_BYTES + 1)
    testing_content = await testing_dataset.read(ADAM_DATASET_MAX_BYTES + 1)

    try:
        return service.queue_training(
            training_content,
            training_dataset.filename or "",
            testing_content,
            testing_dataset.filename or "",
            dataset_category,
        )
    except datasets_service.DatasetUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except datasets_service.DatasetStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except datasets_service.DatasetStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="The training work request could not be queued.",
        ) from exc

def api_text_classification(dataset_category: str | None = None) -> dict[str, object]:
    """Return active classifier details, optionally for its dataset category."""
    try:
        return {"training": service.active_training(dataset_category)}
    except TextClassificationStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def api_delete_text_classification(training_uid: str) -> dict[str, object]:
    """Queue deletion of the active model and its training artifacts."""
    try:
        active_training = service.active_training()
    except TextClassificationStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if active_training is None:
        raise HTTPException(status_code=404, detail="No trained text classification model is available.")
    if active_training["training_uid"] != training_uid:
        raise HTTPException(status_code=409, detail="The active text classification model has changed.")

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
    """Return a trained model's evaluation chart."""
    try:
        path = service.evaluation_chart(training_uid, dataset_category)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TextClassificationStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})
