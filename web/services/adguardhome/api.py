"""AdGuard Home configuration persistence for the web layer."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

from core import db
from core.constants import ADGUARD_HOME_DB_PATH
from web.services.api import service_status_by_name


BOOLEAN_FIELDS = (
    "protection_enabled",
    "filtering_enabled",
    "safe_browsing_enabled",
    "parental_enabled",
    "safe_search_enabled",
    "query_log_enabled",
)


def _bool(value: Any) -> bool:
    return bool(int(value or 0))


def _dns_servers(value: Any, field_name: str) -> list[str]:
    values = value if isinstance(value, list) else str(value or "").replace(",", " ").split()
    servers = [str(item).strip() for item in values if str(item).strip()]
    if field_name == "upstream_dns_servers" and not servers:
        raise HTTPException(status_code=400, detail="At least one upstream DNS server is required.")
    return servers


def _port(value: Any, field_name: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a port number.") from exc
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=400, detail=f"{field_name} must be between 1 and 65535.")
    return port


def _interval(value: Any, field_name: str, maximum: int) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer.") from exc
    if not 1 <= interval <= maximum:
        raise HTTPException(status_code=400, detail=f"{field_name} must be between 1 and {maximum}.")
    return interval


def _settings(row: dict[str, Any]) -> dict[str, Any]:
    settings = dict(row)
    for field in BOOLEAN_FIELDS:
        settings[field] = _bool(settings[field])
    for field in ("upstream_dns_servers", "fallback_dns_servers", "bootstrap_dns_servers"):
        settings[field] = json.loads(settings.pop(f"{field}_json"))
    settings["pending_apply"] = _bool(settings["pending_apply"])
    return settings


def get_config() -> dict[str, Any]:
    """Return persisted AdGuard Home configuration and service state."""
    with db.connection(ADGUARD_HOME_DB_PATH) as conn:
        row = db.fetch_one_on(conn, "SELECT * FROM adguardhome_settings WHERE id = 1")
        filters = db.fetch_all_on(conn, "SELECT * FROM adguardhome_filters ORDER BY id")
        rules = db.fetch_all_on(conn, "SELECT * FROM adguardhome_rules ORDER BY id")
        rewrites = db.fetch_all_on(conn, "SELECT * FROM adguardhome_rewrites ORDER BY domain, answer")
    if row is None:
        raise RuntimeError("AdGuard Home settings are not initialized.")
    return {
        "settings": _settings(row),
        "filters": filters,
        "rules": rules,
        "rewrites": rewrites,
        "service": service_status_by_name("adguardhome"),
    }


def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist AdGuard Home global settings."""
    upstreams = _dns_servers(payload.get("upstream_dns_servers"), "upstream_dns_servers")
    fallback = _dns_servers(payload.get("fallback_dns_servers"), "fallback_dns_servers")
    bootstrap = _dns_servers(payload.get("bootstrap_dns_servers"), "bootstrap_dns_servers")
    values = {
        "dns_bind_host": str(payload.get("dns_bind_host") or "127.0.0.1").strip(),
        "dns_port": _port(payload.get("dns_port"), "dns_port"),
        "web_bind_host": str(payload.get("web_bind_host") or "127.0.0.1").strip(),
        "web_port": _port(payload.get("web_port"), "web_port"),
        "filter_update_interval_hours": _interval(payload.get("filter_update_interval_hours"), "filter_update_interval_hours", 720),
        "query_log_retention_hours": _interval(payload.get("query_log_retention_hours"), "query_log_retention_hours", 8760),
        "statistics_interval_hours": _interval(payload.get("statistics_interval_hours"), "statistics_interval_hours", 720),
    }
    if not values["dns_bind_host"] or not values["web_bind_host"]:
        raise HTTPException(status_code=400, detail="Bind hosts cannot be empty.")
    values.update({field: int(bool(payload.get(field))) for field in BOOLEAN_FIELDS})
    values.update(
        {
            "upstream_dns_servers_json": json.dumps(upstreams),
            "fallback_dns_servers_json": json.dumps(fallback),
            "bootstrap_dns_servers_json": json.dumps(bootstrap),
        }
    )
    assignments = ", ".join(f"{field} = ?" for field in values)
    with db.transaction(ADGUARD_HOME_DB_PATH) as conn:
        db.execute_on(
            conn,
            f"UPDATE adguardhome_settings SET {assignments}, pending_apply = 1, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            tuple(values.values()),
        )
    return get_config()


def add_filter(payload: dict[str, Any]) -> dict[str, Any]:
    """Add one remote AdGuard Home filter source."""
    name = str(payload.get("name") or "").strip()
    source_url = str(payload.get("source_url") or "").strip()
    parsed = urlparse(source_url)
    if not name or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Filter name and an HTTP(S) source URL are required.")
    with db.transaction(ADGUARD_HOME_DB_PATH) as conn:
        db.execute_on(conn, "INSERT INTO adguardhome_filters (name, source_url) VALUES (?, ?)", (name, source_url))
    return get_config()


def delete_filter(filter_id: int) -> dict[str, Any]:
    """Remove one remote filter source."""
    with db.transaction(ADGUARD_HOME_DB_PATH) as conn:
        db.execute_on(conn, "DELETE FROM adguardhome_filters WHERE id = ?", (filter_id,))
    return get_config()
