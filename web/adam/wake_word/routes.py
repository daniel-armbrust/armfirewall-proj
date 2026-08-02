"""Route declarations for ADAM wake-word profiles."""

from fastapi import APIRouter, Request

from .api import api_get_wake_word_profile, api_save_wake_word_profile
from .models import AdamWakeWordProfilePayload


router = APIRouter()


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
