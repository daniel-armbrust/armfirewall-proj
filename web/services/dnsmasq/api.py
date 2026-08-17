"""Compatibility facade for DNSMasq web routes and one-shot executor."""

from .configuration import render_config, validate_dnsmasq_syntax
from .repository import load_config_from_db
from .service import (
    add_static_lease,
    get_dhcp_leases,
    get_dnsmasq_config,
    get_dnsmasq_work_requests,
    save_dnsmasq_config,
    test_dnsmasq_config,
)

__all__ = [
    "add_static_lease", "get_dhcp_leases", "get_dnsmasq_config",
    "get_dnsmasq_work_requests", "load_config_from_db", "render_config",
    "save_dnsmasq_config", "test_dnsmasq_config", "validate_dnsmasq_syntax",
]
