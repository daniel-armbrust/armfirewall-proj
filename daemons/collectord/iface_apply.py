"""One-shot executor for network interface kernel proc work requests."""

from __future__ import annotations

import argparse
import sys

from core import log as logger
from core.constants import COLLECTORD_LOG_SOURCE, IFACE_PROC_WORK_REQUEST_ACTION, IFACE_PROC_WORK_REQUEST_CATEGORY
from core.payload import decode_json_payload

from .collectors.iface.applier import apply_interface_config, apply_proc_value


def build_parser() -> argparse.ArgumentParser:
    """Build the standard work request executor argument parser."""
    parser = argparse.ArgumentParser(description="ArmFirewall interface kernel proc executor.")
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
    """Apply one queued network interface kernel proc change."""
    args = build_parser().parse_args()
    if args.category_name != IFACE_PROC_WORK_REQUEST_CATEGORY or args.action_name != IFACE_PROC_WORK_REQUEST_ACTION:
        raise ValueError("Unsupported network interface work request.")
    payload = decode_json_payload(args.payload_json)
    if payload.get("operation") == "interface_config":
        apply_interface_config(payload)
        logger.info(f"Applied network interface configuration work request {args.work_request_id}.", source=COLLECTORD_LOG_SOURCE)
    else:
        apply_proc_value(payload)
        logger.info(f"Applied network interface kernel proc work request {args.work_request_id}.", source=COLLECTORD_LOG_SOURCE)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd records executor failures.
        logger.error(str(exc), source=COLLECTORD_LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
