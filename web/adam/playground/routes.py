"""Route declarations for ADAM Playground."""

from fastapi import APIRouter

from .api import api_playground_text_classification
from .models import AdamPlaygroundInferencePayload


router = APIRouter()


@router.post("/api/adam/playground/text-classification")
def playground_text_classification(
    payload: AdamPlaygroundInferencePayload,
) -> dict[str, object]:
    """Run text-classification inference for Playground input."""
    return api_playground_text_classification(payload)
