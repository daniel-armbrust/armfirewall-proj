"""HTTP route for ADAM Playground text-classification inference."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from web.adam.models import AdamPlaygroundInferencePayload
from web.adam.playground import PlaygroundInferenceError, infer_text_classification


router = APIRouter()


@router.post("/api/adam/playground/text-classification")
def api_playground_text_classification(
    payload: AdamPlaygroundInferencePayload,
) -> dict[str, object]:
    """Run the active shared model for a Playground text request."""
    try:
        return infer_text_classification(payload.text).to_dict()
    except PlaygroundInferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = ["api_playground_text_classification", "router"]
