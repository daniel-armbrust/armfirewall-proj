"""ADAM dataset API route declarations."""

from __future__ import annotations

from fastapi import APIRouter, Request

from web.adam.datasets.api import api_dataset, api_upload_dataset


router = APIRouter()


@router.get("/api/adam/dataset")
def get_dataset(dataset_category: str) -> dict[str, object]:
    """Return the latest uploaded ADAM dataset for one ADAM category."""
    return api_dataset(dataset_category)


@router.post("/api/adam/dataset")
async def upload_dataset(
    request: Request,
    dataset_category: str,
    dataset_type: str,
) -> dict[str, object]:
    """Upload an ADAM training or testing CSV."""
    return await api_upload_dataset(request, dataset_category, dataset_type)
