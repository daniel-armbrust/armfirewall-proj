"""ADAM dataset business rules and persistence helpers.

The small wrappers preserve the historical ``web.adam.datasets`` import
surface, including the constants used by the existing test suite.
"""

from . import datasets as _implementation
from .datasets import DatasetStateError, DatasetStorageError, DatasetUploadError
from core.constants import ADAM_DATASET_DIR, ADAM_DB_PATH


def _sync_testable_paths() -> None:
    """Propagate compatibility-overridden paths to the implementation module."""
    _implementation.ADAM_DATASET_DIR = ADAM_DATASET_DIR
    _implementation.ADAM_DB_PATH = ADAM_DB_PATH


def store_dataset(*args, **kwargs):
    """Store a dataset using the package compatibility paths."""
    _sync_testable_paths()
    return _implementation.store_dataset(*args, **kwargs)


def latest_dataset(*args, **kwargs):
    """Return the latest dataset using the package compatibility paths."""
    _sync_testable_paths()
    return _implementation.latest_dataset(*args, **kwargs)


def prepare_training(*args, **kwargs):
    """Prepare training using the package compatibility paths."""
    _sync_testable_paths()
    return _implementation.prepare_training(*args, **kwargs)


def restore_uploaded(*args, **kwargs):
    """Restore uploaded datasets using the package compatibility paths."""
    _sync_testable_paths()
    return _implementation.restore_uploaded(*args, **kwargs)

__all__ = [
    "DatasetStateError",
    "DatasetStorageError",
    "DatasetUploadError",
    "latest_dataset",
    "prepare_training",
    "restore_uploaded",
    "store_dataset",
]
