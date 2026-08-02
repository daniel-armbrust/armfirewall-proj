"""HTTP routes for ADAM dataset uploads and training requests."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import HTTPException, Request

from core.constants import (
    ADAM_DATASET_MAX_BYTES,
)
from web.adam.datasets import service


def api_dataset(dataset_category: str) -> dict[str, object]:
    """Return the latest uploaded ADAM dataset."""
    try:
        return {"dataset": service.latest_dataset(dataset_category)}
    except service.DatasetUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except service.DatasetStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def api_upload_dataset(
    request: Request,
    dataset_category: str,
    dataset_type: str,
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
        dataset = service.store_dataset(
            bytes(content), original_filename, dataset_type, dataset_category
        )
    except service.DatasetUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except service.DatasetStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.DatasetStorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "message": f"{dataset_type.strip().capitalize()} dataset loaded successfully.",
        "dataset": dataset,
    }


__all__ = ["api_dataset", "api_upload_dataset"]