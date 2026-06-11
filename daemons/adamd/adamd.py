#!/usr/bin/env python3
"""Execute one asynchronous ADAM model training work request."""

from __future__ import annotations

import argparse
import sys

from core import log as logger
from core.constants import ADAM_MODELS_DIR
from core.payload import decode_json_payload

from .constants import LOG_SOURCE
from .request import AdamWorkRequest
from .worker import run_training_request


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


def request_from_args(args: argparse.Namespace) -> AdamWorkRequest:
    """Create an ADAM request from dispatcher arguments."""
    return AdamWorkRequest(
        work_request_id=args.work_request_id,
        request_uid=args.request_uid,
        category_name=args.category_name,
        category=args.category,
        family=args.family,
        target_name=args.target_name,
        action_name=args.action_name,
        target_rule_id=args.target_rule_id,
        payload=decode_json_payload(args.payload_json),
    )


def validate_request(request: AdamWorkRequest) -> None:
    """Reject work requests that are not ADAM training operations."""
    if request.target_name != "model_training":
        raise ValueError(f"Unsupported ADAM target: {request.target_name}")
    if request.action_name != "train":
        raise ValueError(f"Unsupported ADAM action: {request.action_name}")


def main(argv: list[str] | None = None) -> int:
    """Process exactly one training request and return its exit status."""
    args = build_parser().parse_args(argv)
    request = request_from_args(args)
    validate_request(request)
    ADAM_MODELS_DIR.mkdir(parents=True, exist_ok=True, mode=0o750)

    logger.info(
        f"Starting ADAM training work request {request.work_request_id}.",
        source=LOG_SOURCE,
    )
    result = run_training_request(request)
    logger.info(
        (
            f"Completed ADAM training work request {request.work_request_id}; "
            f"published model {result['model_file']}."
        ),
        source=LOG_SOURCE,
    )
    return 0


def entrypoint(argv: list[str] | None = None) -> int:
    """Run one request and expose failures to workreqd through the exit code."""
    try:
        return main(argv)
    except Exception as exc:  # noqa: BLE001 - dispatcher needs a concise failure.
        message = f"ADAM training request failed: {exc}"
        logger.error(message, source=LOG_SOURCE)
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(entrypoint())
