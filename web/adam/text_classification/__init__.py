"""ADAM text-classification business rules.

Compatibility wrappers keep the historical module-level paths patchable by
the existing tests and callers.
"""

from . import text_classification as _implementation
from .text_classification import TextClassificationStorageError
from core.constants import ADAM_CHARTS_DIR, ADAM_DB_PATH, ROOT_DIR


def _sync_testable_paths() -> None:
    """Propagate compatibility-overridden paths to the implementation module."""
    _implementation.ADAM_CHARTS_DIR = ADAM_CHARTS_DIR
    _implementation.ADAM_DB_PATH = ADAM_DB_PATH
    _implementation.ROOT_DIR = ROOT_DIR


def active_training(*args, **kwargs):
    """Return training metadata using package compatibility paths."""
    _sync_testable_paths()
    return _implementation.active_training(*args, **kwargs)


def evaluation_chart(*args, **kwargs):
    """Resolve the evaluation chart using package compatibility paths."""
    _sync_testable_paths()
    return _implementation.evaluation_chart(*args, **kwargs)

__all__ = [
    "TextClassificationStorageError",
    "active_training",
    "evaluation_chart",
]
