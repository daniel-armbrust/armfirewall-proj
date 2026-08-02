"""Route declarations for ADAM text classification."""

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from .api import (
    api_delete_text_classification,
    api_queue_training,
    api_text_classification,
    api_text_classification_chart,
)


router = APIRouter()


@router.get("/api/adam/text-classification")
def get_text_classification(dataset_category: str | None = None) -> dict[str, object]:
    """Return active text-classification details."""
    return api_text_classification(dataset_category)


@router.delete("/api/adam/text-classification")
def delete_text_classification(training_uid: str) -> dict[str, object]:
    """Queue deletion of the active text classifier."""
    return api_delete_text_classification(training_uid)


@router.get("/api/adam/text-classification/chart", response_class=FileResponse)
def get_text_classification_chart(
    training_uid: str,
    dataset_category: str | None = None,
) -> FileResponse:
    """Return an ADAM evaluation chart."""
    return api_text_classification_chart(training_uid, dataset_category)


@router.post("/api/adam/text-classification/training")
async def queue_training(
    dataset_category: str = Form(...),
    training_dataset: UploadFile = File(...),
    testing_dataset: UploadFile = File(...),
) -> dict[str, object]:
    """Receive a selected pair and queue text-classifier training."""
    return await api_queue_training(training_dataset, testing_dataset, dataset_category)
