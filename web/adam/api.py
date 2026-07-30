"""Compatibility exports for ADAM HTTP handlers.

Route declarations live in :mod:`web.adam.routes`.
"""

from __future__ import annotations

from web.adam.api_datasets import api_dataset, api_training, api_upload_dataset
from web.adam.api_playground import api_playground_text_classification
from web.adam.api_text_classification import (
    api_delete_text_classification,
    api_text_classification,
    api_text_classification_chart,
)
from web.adam.api_transcription import api_receive_transcription
from web.adam.routes import adam_page, router


# Keep the existing import surface available to callers and tests while the
# implementation is organized in one module per API capability.
__all__ = [
    "api_dataset",
    "api_delete_text_classification",
    "api_playground_text_classification",
    "api_receive_transcription",
    "api_text_classification",
    "api_text_classification_chart",
    "api_training",
    "api_upload_dataset",
    "router",
]
