"""Service catalog wrappers used by the service management daemon."""

from __future__ import annotations

from core.service_catalog import optional_service_for_daemon, service_exists

__all__ = ["optional_service_for_daemon", "service_exists"]
