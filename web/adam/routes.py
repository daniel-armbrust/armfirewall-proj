"""Route declarations for the ADAM user interface and APIs."""

from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse

from web.adam import views
from web.adam.api_datasets import api_dataset, api_training, api_upload_dataset
from web.adam.api_playground import api_playground_text_classification
from web.adam.api_text_classification import (
    api_delete_text_classification,
    api_text_classification,
    api_text_classification_chart,
)
from web.adam.api_transcription import api_receive_transcription
from web.adam.api_wake_word import api_get_wake_word_profile, api_save_wake_word_profile
from web.adam.models import (
    AdamPlaygroundInferencePayload,
    AdamTranscriptionPayload,
    AdamWakeWordProfilePayload,
)
from web.adam.websocket import adam_websocket


router = APIRouter()


@router.get("/armfirewall/adam", response_class=HTMLResponse)
def adam_page(request: Request) -> HTMLResponse:
    """Render the ADAM page."""
    return views.render_adam(request)


@router.get("/api/adam/dataset")
def get_dataset(dataset_category: str = "firewall") -> dict[str, object]:
    """Return the latest uploaded dataset for one ADAM category."""
    return api_dataset(dataset_category)


@router.post("/api/adam/dataset")
async def upload_dataset(
    request: Request,
    dataset_type: str = "training",
    dataset_category: str = "firewall",
) -> dict[str, object]:
    """Upload an ADAM training or testing CSV."""
    return await api_upload_dataset(request, dataset_type, dataset_category)


@router.post("/api/adam/training")
def queue_training(dataset_category: str = "firewall") -> dict[str, object]:
    """Queue shared ADAM text-classifier training."""
    return api_training(dataset_category)


@router.get("/api/adam/text-classification")
def get_text_classification(
    dataset_category: str | None = None,
) -> dict[str, object]:
    """Return shared-model details for all data or one category."""
    return api_text_classification(dataset_category)


@router.delete("/api/adam/text-classification")
def delete_text_classification(training_uid: str) -> dict[str, object]:
    """Queue deletion of the active shared text-classifier model."""
    return api_delete_text_classification(training_uid)


@router.get("/api/adam/text-classification/chart", response_class=FileResponse)
def get_text_classification_chart(
    training_uid: str,
    dataset_category: str | None = None,
) -> FileResponse:
    """Return an ADAM evaluation chart."""
    return api_text_classification_chart(training_uid, dataset_category)


@router.post("/api/adam/playground/text-classification")
def playground_text_classification(
    payload: AdamPlaygroundInferencePayload,
) -> dict[str, object]:
    """Run the active shared model for Playground input."""
    return api_playground_text_classification(payload)


@router.post("/api/adam/transcription")
def receive_transcription(
    payload: AdamTranscriptionPayload,
) -> dict[str, str]:
    """Receive a browser voice transcription."""
    return api_receive_transcription(payload)


@router.get("/api/adam/wake-word")
def get_wake_word_profile(request: Request, profile_key: str) -> dict[str, object]:
    """Load the authenticated user's wake-word profile."""
    return api_get_wake_word_profile(request, profile_key)


@router.put("/api/adam/wake-word")
def save_wake_word_profile(
    request: Request,
    payload: AdamWakeWordProfilePayload,
) -> dict[str, object]:
    """Store the authenticated user's wake-word profile."""
    return api_save_wake_word_profile(request, payload)


@router.websocket("/ws/adam")
async def adam_command_websocket(websocket: WebSocket) -> None:
    """Keep the authenticated ADAM command WebSocket open."""
    await adam_websocket(websocket)
