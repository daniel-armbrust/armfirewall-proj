#!/usr/bin/env python3
"""Receive one ADAM work request dispatched by workreqd."""

from __future__ import annotations

import argparse
import sys

from core import log as logger
from core.constants import (
    ADAM_LOG_SOURCE,
    ADAM_WORK_REQUEST_ACTION,
    ADAM_WORK_REQUEST_CATEGORY,
    ADAM_WORK_REQUEST_TARGET,
)
from core.payload import decode_json_payload

from .text_classifier import (
    mark_training_failed,
    mark_training_running,
    train_text_classifier,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the standard work request argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-request-id", required=True)
    parser.add_argument("--request-uid", required=True)
    parser.add_argument("--category-name", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--target-name", required=True)
    parser.add_argument("--action-name", required=True)
    parser.add_argument("--target-rule-id", default="")
    parser.add_argument("--payload-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Receive and execute one text classifier training request."""
    args = build_parser().parse_args(argv)
    payload = decode_json_payload(args.payload_json)

    if args.category_name != ADAM_WORK_REQUEST_CATEGORY:
        raise ValueError(f"Unsupported ADAM category: {args.category_name}")

    if args.target_name != ADAM_WORK_REQUEST_TARGET:
        raise ValueError(f"Unsupported ADAM target: {args.target_name}")

    if args.action_name != ADAM_WORK_REQUEST_ACTION:
        raise ValueError(f"Unsupported ADAM action: {args.action_name}")

    training_uid = str(payload.get("training_uid") or "")

    logger.info(
        (
            f"Starting ADAM text classifier training for work request "
            f"{args.work_request_id}."
        ),
        source=ADAM_LOG_SOURCE,
    )

    mark_training_running(training_uid, args.request_uid)

    try:
        result = train_text_classifier(training_uid, args.request_uid)
    except Exception as exc:
        try:
            mark_training_failed(training_uid, args.request_uid, str(exc))
        except Exception as status_exc:  # noqa: BLE001 - preserve original failure.
            logger.error(
                f"Could not persist ADAM training failure: {status_exc}",
                source=ADAM_LOG_SOURCE,
            )

        raise

    logger.info(
        (
            f"Completed ADAM text classifier training for work request "
            f"{args.work_request_id}; testing accuracy="
            f"{result['testing_accuracy']:.4f}."
        ),
        source=ADAM_LOG_SOURCE,
    )
    return 0


def entrypoint(argv: list[str] | None = None) -> int:
    """Expose invocation failures to workreqd through the exit code."""
    try:
        return main(argv)
    except Exception as exc:  # noqa: BLE001 - dispatcher needs a concise failure.
        message = f"ADAM work request failed: {exc}"
        logger.error(message, source=ADAM_LOG_SOURCE)
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(entrypoint())
