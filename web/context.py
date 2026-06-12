"""Shared template context helpers for the ArmFirewall Web layer."""

from __future__ import annotations

from typing import Any

from core import db
from core.constants import (
    ADAM_LISTENING_STORAGE_KEY,
    ADAM_COMMAND_MIN_CAPTURE_MS,
    ADAM_COMMAND_SAMPLE_RATE,
    ADAM_COMMAND_SILENCE_THRESHOLD,
    ADAM_COMMAND_TIMEOUT_MS,
    ADAM_COMMAND_TRAILING_SILENCE_MS,
    ADAM_SPEECH_LANGUAGE,
    ADAM_WAKE_DETECTION_INTERVAL_MS,
    ADAM_WAKE_DETECTION_STREAK,
    ADAM_WAKE_DETECTION_THRESHOLD_MULTIPLIER,
    ADAM_WAKE_DETECTOR_WORKER_URL,
    ADAM_WAKE_ENROLLMENT_DURATION_MS,
    ADAM_WAKE_ENROLLMENT_SAMPLES,
    ADAM_WAKE_PRE_ROLL_MS,
    ADAM_WAKE_PROFILE_KEY,
    ADAM_WAKE_TRANSCRIPTION_ALIASES,
    ADAM_WAKE_WORD,
    ADAM_WAKE_WORD_ALIASES,
    ADAM_WAKE_WORD_ENGINE_URL,
    ADAM_WAKE_WORD_MIN_CONFIDENCE,
    ADAM_WAKE_WORD_MODEL_URL,
    ADAM_WAKE_WORD_WORKLET_URL,
)
from web.services.api import service_installed


def menu_context() -> dict[str, Any]:
    """Return dynamic menu state for template rendering."""
    try:
        squid_installed = service_installed("squid")
    except (FileNotFoundError, db.DatabaseError):
        squid_installed = False

    try:
        libreswan_installed = service_installed("libreswan")
    except (FileNotFoundError, db.DatabaseError):
        libreswan_installed = False

    return {
        "squid_installed": squid_installed,
        "libreswan_installed": libreswan_installed,
        "adam_listening_storage_key": ADAM_LISTENING_STORAGE_KEY,
        "adam_command_min_capture_ms": ADAM_COMMAND_MIN_CAPTURE_MS,
        "adam_command_sample_rate": ADAM_COMMAND_SAMPLE_RATE,
        "adam_command_silence_threshold": ADAM_COMMAND_SILENCE_THRESHOLD,
        "adam_command_timeout_ms": ADAM_COMMAND_TIMEOUT_MS,
        "adam_command_trailing_silence_ms": ADAM_COMMAND_TRAILING_SILENCE_MS,
        "adam_speech_language": ADAM_SPEECH_LANGUAGE,
        "adam_wake_detection_interval_ms": ADAM_WAKE_DETECTION_INTERVAL_MS,
        "adam_wake_detection_streak": ADAM_WAKE_DETECTION_STREAK,
        "adam_wake_detection_threshold_multiplier": ADAM_WAKE_DETECTION_THRESHOLD_MULTIPLIER,
        "adam_wake_detector_worker_url": ADAM_WAKE_DETECTOR_WORKER_URL,
        "adam_wake_enrollment_duration_ms": ADAM_WAKE_ENROLLMENT_DURATION_MS,
        "adam_wake_enrollment_samples": ADAM_WAKE_ENROLLMENT_SAMPLES,
        "adam_wake_pre_roll_ms": ADAM_WAKE_PRE_ROLL_MS,
        "adam_wake_profile_key": ADAM_WAKE_PROFILE_KEY,
        "adam_wake_transcription_aliases": ADAM_WAKE_TRANSCRIPTION_ALIASES,
        "adam_wake_word": ADAM_WAKE_WORD,
        "adam_wake_word_aliases": ADAM_WAKE_WORD_ALIASES,
        "adam_wake_word_engine_url": ADAM_WAKE_WORD_ENGINE_URL,
        "adam_wake_word_min_confidence": ADAM_WAKE_WORD_MIN_CONFIDENCE,
        "adam_wake_word_model_url": ADAM_WAKE_WORD_MODEL_URL,
        "adam_wake_word_worklet_url": ADAM_WAKE_WORD_WORKLET_URL,
    }
