"""HTTP routes for ADAM."""

from __future__ import annotations

from urllib.parse import unquote
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from core.constants import (
    ADAM_DATASET_MAX_BYTES,
    ADAM_WORK_REQUEST_ACTION,
    ADAM_WORK_REQUEST_CATEGORY,
    ADAM_WORK_REQUEST_DELETE_ACTION,
)
from web.adam import datasets, models, text_classification, views
from web.workrequests import api as workrequests_api


router = APIRouter()


@router.get("/armfirewall/adam", response_class=HTMLResponse)
def adam_page(request: Request) -> HTMLResponse:
    """Render the ADAM page."""
    return views.render_adam(request)


@router.post("/api/adam/transcription")
def api_receive_transcription(
    payload: models.AdamTranscriptionPayload,
) -> dict[str, str]:
    """Receive an ADAM voice transcription without processing it."""
    return {"status": "received"}


@router.get("/api/adam/dataset")
def api_dataset(dataset_category: str = "firewall") -> dict[str, object]:
    """Return the latest uploaded ADAM dataset."""
    try:
        return {"dataset": datasets.latest_dataset(dataset_category)}
    except datasets.DatasetUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except datasets.DatasetStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/adam/dataset")
async def api_upload_dataset(
    request: Request,
    dataset_type: str = "training",
    dataset_category: str = "firewall",
) -> dict[str, object]:
    """Receive one ADAM training or testing CSV upload."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()

    if content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(status_code=415, detail="Upload a file in CSV format.")

    content = bytearray()

    async for chunk in request.stream():
        content.extend(chunk)

        if len(content) > ADAM_DATASET_MAX_BYTES:
            raise HTTPException(status_code=413, detail="The CSV file exceeds the 5 MB limit.")

    original_filename = unquote(request.headers.get("x-file-name", ""))
    
    try:
        dataset = datasets.store_dataset(
            bytes(content),
            original_filename,
            dataset_type,
            dataset_category,
        )
    except datasets.DatasetUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except datasets.DatasetStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except datasets.DatasetStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "message": f"{dataset_type.strip().capitalize()} dataset loaded successfully.",
        "dataset": dataset,
    }


@router.post("/api/adam/training")
def api_training(dataset_category: str = "firewall") -> dict[str, object]:
    """Queue asynchronous ADAM model training for the active dataset pair."""
    request_uid = str(uuid4())

    try:
        dataset = datasets.prepare_training(request_uid, dataset_category)
    except datasets.DatasetUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except datasets.DatasetStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except datasets.DatasetStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        work_request_id = workrequests_api.queue_work_request(
            action=ADAM_WORK_REQUEST_ACTION,
            category_name=ADAM_WORK_REQUEST_CATEGORY,
            source="gui",
            priority=80,
            request_uid=request_uid,
            allowed_actions=(ADAM_WORK_REQUEST_ACTION,),
            allowed_categories=(ADAM_WORK_REQUEST_CATEGORY,),
            event_message="Queued ADAM intent classifier training.",
            payload={
                "training_uid": dataset["training_uid"],
                "dataset_ids": [
                    item["dataset_id"] for item in dataset["datasets"]
                ],
                "dataset_categories": sorted(
                    {item["category"] for item in dataset["datasets"]}
                ),
            },
        )
    except Exception as exc:
        try:
            datasets.restore_uploaded(request_uid)
        except datasets.DatasetStorageError:
            pass

        raise HTTPException(
            status_code=500,
            detail="The training work request could not be queued.",
        ) from exc

    return {
        "message": "Training work request queued successfully.",
        "status": "queue",
        "work_request_id": work_request_id,
        "request_uid": request_uid,
        "dataset": dataset,
    }


@router.get("/api/adam/text-classification")
def api_text_classification() -> dict[str, object]:
    """Return details for the active trained text classifier."""
    try:
        return {"training": text_classification.active_training()}
    except text_classification.TextClassificationStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/adam/text-classification")
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


@router.get("/api/adam/text-classification/chart", response_class=FileResponse)
def api_text_classification_chart(training_uid: str) -> FileResponse:
    """Return the active classifier evaluation chart."""
    try:
        chart_path = text_classification.evaluation_chart(training_uid)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except text_classification.TextClassificationStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FileResponse(
        chart_path,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
