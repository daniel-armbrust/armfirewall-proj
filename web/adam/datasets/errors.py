"""ADAM dataset domain errors."""

from __future__ import annotations


class DatasetUploadError(ValueError):
    """Represent an invalid ADAM dataset upload."""


class DatasetStorageError(RuntimeError):
    """Represent an ADAM dataset persistence failure."""


class DatasetStateError(RuntimeError):
    """Represent an invalid transition in the ADAM dataset workflow."""

