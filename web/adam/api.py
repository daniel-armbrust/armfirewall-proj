"""Web routes for the ADAM assistant."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from core.adam import datasets
from web.adam import views


router = APIRouter()


@router.get("/armfirewall/ia", response_class=HTMLResponse)
def adam_page(request: Request) -> HTMLResponse:
    """Render the ADAM assistant page."""
    return views.render_adam(request)


@router.get("/api/adam/training-dataset")
def api_training_dataset() -> dict[str, object]:
    """Return metadata for the current ADAM training dataset."""
    try:
        return {"dataset": datasets.training_dataset_info()}
    except datasets.DatasetValidationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/adam/training-dataset")
async def api_upload_training_dataset(request: Request) -> dict[str, object]:
    """Validate and store one CSV as the active ADAM training dataset."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(status_code=415, detail="Upload a file in CSV format.")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > datasets.MAX_DATASET_BYTES:
                raise HTTPException(status_code=413, detail="The CSV file exceeds the 5 MB limit.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header.")

    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > datasets.MAX_DATASET_BYTES:
            raise HTTPException(status_code=413, detail="The CSV file exceeds the 5 MB limit.")

    original_name = unquote(request.headers.get("x-file-name", "")).strip()
    if original_name and not original_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="The file name must end with .csv.")

    try:
        dataset = datasets.save_training_dataset(
            bytes(content),
            original_name=original_name,
        )
    except datasets.DatasetValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="The dataset could not be stored.") from exc

    return {
        "message": "Training dataset imported successfully.",
        "dataset": dataset,
    }
