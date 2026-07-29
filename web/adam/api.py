"""ADAM HTTP route aggregator."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.adam import views
from web.adam.api_datasets import (
    api_dataset,
    api_training,
    api_upload_dataset,
    router as datasets_router,
)
from web.adam.api_text_classification import (
    api_delete_text_classification,
    api_text_classification,
    api_text_classification_chart,
    router as text_classification_router,
)
from web.adam.api_transcription import (
    api_receive_transcription,
    router as transcription_router,
)
from web.adam.websocket import router as websocket_router


router = APIRouter()
router.include_router(transcription_router)
router.include_router(datasets_router)
router.include_router(text_classification_router)
router.include_router(websocket_router)


@router.get("/armfirewall/adam", response_class=HTMLResponse)
def adam_page(request: Request) -> HTMLResponse:
    """Render the ADAM page."""
    return views.render_adam(request)


# Keep the existing import surface available to callers and tests while the
# implementation is organized in one module per API capability.
__all__ = [
    "api_dataset",
    "api_delete_text_classification",
    "api_receive_transcription",
    "api_text_classification",
    "api_text_classification_chart",
    "api_training",
    "api_upload_dataset",
    "router",
]
