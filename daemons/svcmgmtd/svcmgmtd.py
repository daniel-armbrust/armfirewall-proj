#!/usr/bin/env python3
"""One-shot optional service package manager used by the work request daemon."""

from __future__ import annotations

import argparse
import sys

from core import log as logger
from core.payload import decode_json_payload

from .actions import control_service, install_service, uninstall_service
from .constants import LOG_SOURCE
from .services import validate_control_service, validate_service


def build_parser() -> argparse.ArgumentParser:
    """Build the work request executor argument parser."""
    parser = argparse.ArgumentParser(description="ArmFirewall optional service package executor.")
    parser.add_argument("--work-request-id", required=True)
    parser.add_argument("--request-uid", required=True)
    parser.add_argument("--category-name", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--family", required=False)
    parser.add_argument("--target-name", required=True)
    parser.add_argument("--action-name", required=True)
    parser.add_argument("--target-rule-id", required=False)
    parser.add_argument("--payload-json", required=True)
    
    return parser


def main() -> int:
    """Execute one service management work request."""
    args = build_parser().parse_args()
    
    if args.category != "SERVICE_MANAGEMENT":
        raise RuntimeError(f"Unsupported category for svcmgmtd.py: {args.category}")
    
    payload = decode_json_payload(args.payload_json)

    if args.action_name == "install":
        service = validate_service(payload)
        install_service(service)
    elif args.action_name == "uninstall":
        service = validate_service(payload)
        uninstall_service(service)
    elif args.action_name in {"start", "stop", "restart"}:
        service = validate_control_service(payload, args.action_name)
        control_service(service, args.action_name)
    else:
        raise RuntimeError(f"Unsupported service management action: {args.action_name}")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd captures stderr.
        logger.error(str(exc), source=LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        sys.exit(1)
