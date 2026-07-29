"""Constants used by the Work Requests web module."""

from __future__ import annotations


SERVICE_WORK_REQUEST_ACTIONS = {"disable", "enable", "install", "uninstall", "start", "stop", "restart"}

SERVICE_WORK_REQUEST_CATEGORIES = {
    "SERVICE_MANAGEMENT.OPTIONAL_SERVICES",
    "SERVICE_MANAGEMENT.SERVICE_CONTROL",
    "SERVICE_MANAGEMENT.LIBRESWAN_CONFIG",
}

WORK_REQUEST_COLUMNS = """
    id,
    request_uid,
    status,
    source,
    category_name,
    action_name,
    target_rule_id,
    priority,
    payload_json,
    error_message,
    created_at,
    updated_at
"""
