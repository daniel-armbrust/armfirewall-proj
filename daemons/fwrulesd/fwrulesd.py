#!/usr/bin/env python3
"""One-shot firewall rule executor used by the work request daemon."""

from __future__ import annotations

import argparse


from core import log as logger
from core.payload import decode_json_payload

from .actions import run_action
from .constants import LOG_SOURCE
from .models import FirewallWorkRequest


def request_from_args(args: argparse.Namespace) -> FirewallWorkRequest:
    """Return a normalized firewall work request from CLI arguments."""
    return FirewallWorkRequest(
        work_request_id=str(args.work_request_id or ""),
        request_uid=str(args.request_uid or ""),
        category_name=str(args.category_name or ""),
        category=str(args.category or ""),
        family=str(args.family or ""),
        target_name=str(args.target_name or ""),
        action_name=str(args.action_name or ""),
        target_rule_id=str(args.target_rule_id or ""),
        payload=decode_json_payload(args.payload_json),
    )


def main() -> int:
    """Execute a single dispatched firewall work request."""
    parser = argparse.ArgumentParser(description="ArmFirewall firewall rule executor.")
    parser.add_argument("--work-request-id")
    parser.add_argument("--request-uid")
    parser.add_argument("--category-name")
    parser.add_argument("--category")
    parser.add_argument("--family")
    parser.add_argument("--target-name")
    parser.add_argument("--action-name")
    parser.add_argument("--target-rule-id")
    parser.add_argument("--payload-json")
    args = request_from_args(parser.parse_args())

    if not args.work_request_id:
        logger.error("Missing --work-request-id for one-shot firewall execution.", source=LOG_SOURCE)
        return 2
    
    return run_action(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logger.error("Firewall rule execution interrupted.", source=LOG_SOURCE)
        raise SystemExit(0)
