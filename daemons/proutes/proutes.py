#!/usr/bin/env python3
"""One-shot policy routing executor used by the work request daemon."""

from __future__ import annotations

import argparse

from core import db
from core import log as logger
from core.workrequest import decode_payload

from .constants import LOG_SOURCE, POLICY_DB_PATH
from .executor import execute_work_request


def verify_policy_database() -> None:
    """Verify that the policy routing database can be opened."""
    db.verify_database(POLICY_DB_PATH)


def run_action(args: argparse.Namespace) -> int:
    """Handle one dispatched policy routing work request."""
    if args.category != "POLICY_ROUTING":
        logger.error(f"Unsupported policy routing category: {args.category}", source=LOG_SOURCE)
        return 2

    try:
        verify_policy_database()
    except Exception as exc:  # noqa: BLE001 - message is returned to workreqd.
        logger.error(f"Could not connect to policy routing database: {exc}", source=LOG_SOURCE)
        return 1

    logger.log(
        "Received work request "
        f"id={args.work_request_id} category={args.category_name} action={args.action_name}.",
        source=LOG_SOURCE,
    )

    try:
        if args.action_name != "apply":
            raise RuntimeError(f"Unsupported policy routing action: {args.action_name}")
        
        payload = decode_payload(args.payload_json)
        applied, removed = execute_work_request(payload)
    except Exception as exc:  # noqa: BLE001 - message is returned to workreqd.
        logger.error(f"Policy routing execution failed: {exc}", source=LOG_SOURCE)
        return 1

    logger.log(f"Policy routing execution completed: applied={applied}, removed={removed}.", source=LOG_SOURCE)
    
    return 0


def main() -> int:
    """Execute a single dispatched policy routing work request."""
    parser = argparse.ArgumentParser(description="ArmFirewall policy routing executor.")
    parser.add_argument("--work-request-id")
    parser.add_argument("--request-uid")
    parser.add_argument("--category-name")
    parser.add_argument("--category")
    parser.add_argument("--family")
    parser.add_argument("--target-name")
    parser.add_argument("--action-name")
    parser.add_argument("--target-rule-id")
    parser.add_argument("--payload-json")
    args = parser.parse_args()

    if not args.work_request_id:
        logger.error("Missing --work-request-id for one-shot policy routing execution.", source=LOG_SOURCE)
        return 2

    return run_action(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.error("Policy routing execution interrupted.", source=LOG_SOURCE)
        raise SystemExit(0)
