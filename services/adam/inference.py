"""Thread-safe inference using the active trusted ADAM model."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import joblib

from core.constants import ADAM_MODELS_DIR

from .models import IntentPrediction


ACTIVE_MODEL_FILE = "active.json"


class ModelUnavailableError(RuntimeError):
    """Raised when no valid active classifier can be loaded."""


class IntentClassifier:
    """Cache and safely reload the active local joblib classifier."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache_key: tuple[str, int] | None = None
        self._model: Any | None = None

    def _active_metadata(self) -> dict[str, Any]:
        active_path = ADAM_MODELS_DIR / ACTIVE_MODEL_FILE
        try:
            metadata = json.loads(active_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ModelUnavailableError("No active ADAM model is available.") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelUnavailableError("The active ADAM model metadata is invalid.") from exc
        if not isinstance(metadata, dict):
            raise ModelUnavailableError("The active ADAM model metadata is invalid.")
        return metadata

    def _load(self) -> tuple[Any, str]:
        metadata = self._active_metadata()
        model_id = str(metadata.get("model_id") or "").strip()
        model_file = str(metadata.get("model_file") or "").strip()
        if not model_id or not model_file or Path(model_file).name != model_file:
            raise ModelUnavailableError("The active ADAM model reference is invalid.")

        model_path = (ADAM_MODELS_DIR / model_file).resolve()
        if model_path.parent != ADAM_MODELS_DIR.resolve() or not model_path.is_file():
            raise ModelUnavailableError("The active ADAM model file is not available.")
        cache_key = (model_id, model_path.stat().st_mtime_ns)

        with self._lock:
            if self._cache_key != cache_key:
                try:
                    model = joblib.load(model_path)
                except Exception as exc:  # noqa: BLE001 - normalize trusted artifact errors.
                    raise ModelUnavailableError(
                        "The active ADAM model could not be loaded."
                    ) from exc
                if not callable(getattr(model, "predict", None)) or not callable(
                    getattr(model, "predict_proba", None)
                ):
                    raise ModelUnavailableError(
                        "The active ADAM model does not support classification."
                    )
                self._model = model
                self._cache_key = cache_key
            return self._model, model_id

    def predict(self, text: str) -> IntentPrediction:
        """Classify one non-empty user message and return its confidence."""
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("The command text cannot be empty.")

        model, model_id = self._load()
        labels = model.predict([normalized_text])
        probabilities = model.predict_proba([normalized_text])[0]
        confidence = float(max(probabilities))
        return IntentPrediction(
            label=str(labels[0]),
            confidence=confidence,
            model_id=model_id,
        )
