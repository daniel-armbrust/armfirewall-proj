"""Validation and normalization for DNSMasq payloads."""
from __future__ import annotations
import ipaddress
import re
from typing import Any
from fastapi import HTTPException
from core.constants import DNSMASQ_ALL_INTERFACES_TOKEN, DNSMASQ_DOMAIN_LABEL_PATTERN
from .configuration import default_config, default_interface_config
from .interfaces import list_interfaces
from .repository import load_config_from_db
DOMAIN_LABEL_RE = re.compile(DNSMASQ_DOMAIN_LABEL_PATTERN)

def validate_ip(value: str, field_name: str) -> str:
    """Validate and normalize one IP address."""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid IP address.") from exc


def validate_optional_ip(value: Any, field_name: str) -> str:
    """Validate an optional IP address field."""
    text = str(value or "").strip()
    return validate_ip(text, field_name) if text else ""


def validate_optional_ipv4(value: Any, field_name: str) -> str:
    """Validate an optional IPv4 address used by a DHCP range."""
    normalized = validate_optional_ip(value, field_name)
    if normalized and ipaddress.ip_address(normalized).version != 4:
        raise HTTPException(status_code=400, detail=f"{field_name} must be an IPv4 address.")
    return normalized


def validate_dns_domain(value: Any, field_name: str) -> str:
    """Validate one DNS domain field."""
    domain = str(value or "armfirewall.local").strip().strip(".")
    labels = domain.split(".")
    if (
        not domain
        or len(domain) > 253
        or ".." in domain
        or len(labels) < 2
        or all(label.isdigit() for label in labels)
        or any(not DOMAIN_LABEL_RE.match(label) for label in labels)
    ):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid DNS domain.")
    return domain


def validate_domain(value: Any) -> str:
    """Validate the local DNS domain."""
    return validate_dns_domain(value, "local_domain")


def validate_interfaces(values: Any) -> list[str]:
    """Validate requested listen interfaces."""
    requested = [str(item).strip() for item in values or [] if str(item).strip()]
    if DNSMASQ_ALL_INTERFACES_TOKEN in requested:
        return [DNSMASQ_ALL_INTERFACES_TOKEN]
    available = {str(item.get("name")) for item in list_interfaces()}
    if available:
        invalid = sorted(set(requested) - available)
        if invalid:
            raise HTTPException(status_code=400, detail=f"Unknown interface(s): {', '.join(invalid)}")
    return requested


def normalize_upstream_list(value: Any, field_name: str) -> list[str]:
    """Validate a list or text block of upstream DNS servers."""
    if isinstance(value, str):
        raw_items = split_server_tokens(value)
    else:
        raw_items = [str(item).strip() for item in value or [] if str(item).strip()]
    return [validate_ip(item, field_name) for item in raw_items]


def validate_domain_upstreams(values: Any) -> list[dict[str, Any]]:
    """Validate domain-specific upstream DNS rules."""
    rules: dict[str, list[str]] = {}
    for item in values or []:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="domain_upstreams entries must be objects.")
        domain = validate_dns_domain(item.get("domain"), "domain_upstreams.domain")
        upstreams = normalize_upstream_list(item.get("upstreams"), "domain_upstreams.upstreams")
        if not upstreams:
            raise HTTPException(status_code=400, detail=f"At least one upstream is required for {domain}.")
        rules.setdefault(domain, [])
        for upstream in upstreams:
            if upstream not in rules[domain]:
                rules[domain].append(upstream)
    return [{"domain": domain, "upstreams": upstreams} for domain, upstreams in sorted(rules.items())]


def normalize_interface_config(item: dict[str, Any]) -> dict[str, Any]:
    """Validate one per-interface dnsmasq configuration."""
    iface_name = validate_interfaces([item.get("iface")])[0]
    config = default_interface_config(iface_name)
    config["dns_enabled"] = False
    config["upstream_dns_servers"] = []
    config["domain_upstreams"] = []
    config["dhcp_enabled"] = bool(item.get("dhcp_enabled"))
    config["dhcp_range_start"] = validate_optional_ipv4(item.get("dhcp_range_start"), f"{iface_name}.dhcp_range_start")
    config["dhcp_range_end"] = validate_optional_ipv4(item.get("dhcp_range_end"), f"{iface_name}.dhcp_range_end")
    config["lease_time"] = validate_lease_time(item.get("lease_time"))
    config["dhcp_authoritative"] = bool(item.get("dhcp_authoritative"))
    config["ipv6_ra_enabled"] = bool(item.get("ipv6_ra_enabled"))
    config["ipv6_ra_names"] = bool(item.get("ipv6_ra_names", True))
    config["ipv6_ra_lifetime"] = validate_lease_time(item.get("ipv6_ra_lifetime") or "4h")

    if config["dhcp_enabled"] and (not config["dhcp_range_start"] or not config["dhcp_range_end"]):
        raise HTTPException(status_code=400, detail=f"DHCP range start and end are required for {iface_name}.")
    if config["dhcp_enabled"]:
        start = ipaddress.ip_address(config["dhcp_range_start"])
        end = ipaddress.ip_address(config["dhcp_range_end"])
        if start.version != end.version or int(start) > int(end):
            raise HTTPException(status_code=400, detail=f"DHCP range for {iface_name} must use one address family and start before end.")
    return config


def normalize_interface_configs(values: Any, fallback: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate per-interface DNS and DHCP settings."""
    if not values:
        configs = []
        for iface_name in fallback["listen_interfaces"]:
            if iface_name == DNSMASQ_ALL_INTERFACES_TOKEN:
                continue
            config = default_interface_config(iface_name)
            config["dhcp_enabled"] = bool(fallback.get("dhcp_enabled"))
            config["dhcp_range_start"] = fallback.get("dhcp_range_start", "")
            config["dhcp_range_end"] = fallback.get("dhcp_range_end", "")
            config["lease_time"] = fallback.get("lease_time", "12h")
            config["dhcp_authoritative"] = bool(fallback.get("dhcp_authoritative"))
            config["ipv6_ra_enabled"] = bool(fallback.get("ipv6_ra_enabled"))
            config["ipv6_ra_names"] = bool(fallback.get("ipv6_ra_names", True))
            config["ipv6_ra_lifetime"] = fallback.get("ipv6_ra_lifetime", "4h")
            configs.append(normalize_interface_config(config))
        return configs
    configs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="interface_configs entries must be objects.")
        config = normalize_interface_config(item)
        if config["iface"] in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate interface config: {config['iface']}.")
        seen.add(config["iface"])
        configs.append(config)
    return configs


def validate_lease_time(value: Any) -> str:
    """Validate a dnsmasq DHCP lease time token."""
    lease_time = str(value or "12h").strip()
    if not re.match(r"^\d+[smhdw]?$|^infinite$", lease_time):
        raise HTTPException(status_code=400, detail="lease_time must be like 12h, 30m, 3600, or infinite.")
    return lease_time


def validate_cache_size(value: Any) -> int:
    """Validate dnsmasq cache size."""
    try:
        cache_size = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="cache_size must be an integer.") from exc
    if cache_size < 0 or cache_size > 1000000:
        raise HTTPException(status_code=400, detail="cache_size must be between 0 and 1000000.")
    return cache_size


def normalize_extra_options(value: Any) -> str:
    """Normalize optional raw dnsmasq directives from the GUI."""
    lines = []
    for line in str(value or "").splitlines():
        item = line.strip()
        if item and item != "-":
            lines.append(item)
    return "\n".join(lines)


def normalize_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize dnsmasq GUI payload."""
    config = default_config()
    has_interface_configs = bool(payload.get("interface_configs"))
    config["dns_enabled"] = bool(payload.get("dns_enabled"))
    config["dhcp_enabled"] = bool(payload.get("dhcp_enabled"))
    config["listen_interfaces"] = validate_interfaces(payload.get("listen_interfaces"))
    config["local_domain"] = validate_domain(payload.get("local_domain"))
    config["upstream_dns_servers"] = normalize_upstream_list(payload.get("upstream_dns_servers"), "upstream_dns_servers")
    config["domain_upstreams"] = validate_domain_upstreams(payload.get("domain_upstreams"))
    config["adguardhome_upstream_enabled"] = bool(payload.get("adguardhome_upstream_enabled"))
    config["dhcp_range_start"] = validate_optional_ipv4(payload.get("dhcp_range_start"), "dhcp_range_start")
    config["dhcp_range_end"] = validate_optional_ipv4(payload.get("dhcp_range_end"), "dhcp_range_end")
    config["lease_time"] = validate_lease_time(payload.get("lease_time"))
    config["cache_size"] = validate_cache_size(payload.get("cache_size", config["cache_size"]))
    config["expand_hosts"] = bool(payload.get("expand_hosts"))
    config["domain_needed"] = bool(payload.get("domain_needed"))
    config["bogus_priv"] = bool(payload.get("bogus_priv"))
    config["dhcp_authoritative"] = bool(payload.get("dhcp_authoritative"))
    config["extra_options"] = normalize_extra_options(payload.get("extra_options"))

    if not config["listen_interfaces"] and not has_interface_configs:
        config["dhcp_enabled"] = False
        config["interface_configs"] = []
        if config["dns_enabled"]:
            # DNS is global and must remain reachable when DHCP has no interface configuration.
            config["listen_interfaces"] = [DNSMASQ_ALL_INTERFACES_TOKEN]
        else:
            config["domain_upstreams"] = []
            return config

    if has_interface_configs:
        config["interface_configs"] = normalize_interface_configs(payload.get("interface_configs"), config)
        config["listen_interfaces"] = [item["iface"] for item in config["interface_configs"]]
        config["dhcp_enabled"] = any(item["dhcp_enabled"] for item in config["interface_configs"])
        return config

    if config["dns_enabled"] and not config["upstream_dns_servers"]:
        raise HTTPException(status_code=400, detail="At least one upstream DNS server is required when DNS is enabled.")
    if config["dhcp_enabled"] and (not config["dhcp_range_start"] or not config["dhcp_range_end"]):
        raise HTTPException(status_code=400, detail="DHCP range start and end are required when DHCP is enabled.")
    if config["dhcp_enabled"]:
        start = ipaddress.ip_address(config["dhcp_range_start"])
        end = ipaddress.ip_address(config["dhcp_range_end"])
        if start.version != end.version or int(start) > int(end):
            raise HTTPException(status_code=400, detail="DHCP range must use one address family and start before end.")

    config["interface_configs"] = normalize_interface_configs(payload.get("interface_configs"), config)
    return config
