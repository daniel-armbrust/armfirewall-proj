"""DNSMasq configuration parsing and rendering."""
from __future__ import annotations
import json
import re
import shutil
import subprocess
from typing import Any
from core.constants import (
    DNSMASQ_ALL_INTERFACES_TOKEN,
    DNSMASQ_BOOL_DEFAULTS,
    DNSMASQ_CONF_PATH,
    DNSMASQ_DNS_PORT,
    DNSMASQ_INTERFACE_CONFIG_PREFIX,
    DNSMASQ_LEASES_PATH,
)

def default_config() -> dict[str, Any]:
    """Return default dnsmasq settings used by ArmFirewall."""
    return {
        "dns_enabled": False,
        "dhcp_enabled": False,
        "listen_interfaces": [],
        "local_domain": "armfirewall.local",
        "upstream_dns_servers": ["1.1.1.1", "8.8.8.8"],
        "domain_upstreams": [],
        "interface_configs": [],
        "adguardhome_upstream_enabled": False,
        "dhcp_range_start": "",
        "dhcp_range_end": "",
        "lease_time": "12h",
        "cache_size": 1000,
        "expand_hosts": DNSMASQ_BOOL_DEFAULTS["expand_hosts"],
        "domain_needed": DNSMASQ_BOOL_DEFAULTS["domain_needed"],
        "bogus_priv": DNSMASQ_BOOL_DEFAULTS["bogus_priv"],
        "dhcp_authoritative": DNSMASQ_BOOL_DEFAULTS["dhcp_authoritative"],
        "ipv6_ra_enabled": False,
        "ipv6_ra_names": True,
        "ipv6_ra_lifetime": "4h",
        "extra_options": "",
        "static_leases": [],
    }


def default_interface_config(iface_name: str) -> dict[str, Any]:
    """Return default DNS and DHCP settings for one interface."""
    return {
        "iface": iface_name,
        "dns_enabled": False,
        "local_domain": "armfirewall.local",
        "upstream_dns_servers": ["1.1.1.1", "8.8.8.8"],
        "domain_upstreams": [],
        "adguardhome_upstream_enabled": False,
        "cache_size": 1000,
        "expand_hosts": DNSMASQ_BOOL_DEFAULTS["expand_hosts"],
        "domain_needed": DNSMASQ_BOOL_DEFAULTS["domain_needed"],
        "bogus_priv": DNSMASQ_BOOL_DEFAULTS["bogus_priv"],
        "dhcp_enabled": False,
        "dhcp_range_start": "",
        "dhcp_range_end": "",
        "lease_time": "12h",
        "dhcp_authoritative": DNSMASQ_BOOL_DEFAULTS["dhcp_authoritative"],
        "ipv6_ra_enabled": False,
        "ipv6_ra_names": True,
        "ipv6_ra_lifetime": "4h",
    }


def interface_config_from_global(iface_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Build one interface config from legacy global settings."""
    item = default_interface_config(iface_name)
    for key in item:
        if key != "iface" and key in config:
            item[key] = config[key]
    return item


def read_config_lines() -> list[str]:
    """Read dnsmasq.conf lines when the file exists."""
    if not DNSMASQ_CONF_PATH.exists():
        return []
    return DNSMASQ_CONF_PATH.read_text(encoding="utf-8").splitlines()


def parse_bool_line(lines: list[str], directive: str, default: bool = False) -> bool:
    """Return whether a boolean dnsmasq directive is present."""
    return any(line.strip() == directive for line in lines) or default and not lines


def split_csv(value: str) -> list[str]:
    """Split comma-separated dnsmasq values."""
    return [part.strip() for part in value.split(",") if part.strip()]


def split_server_tokens(value: str) -> list[str]:
    """Split server lists from GUI text fields."""
    return [part.strip() for part in re.split(r"[\s,]+", value) if part.strip()]


def parse_domain_server(value: str) -> tuple[str, str] | None:
    """Parse a dnsmasq domain-specific server directive."""
    if not value.startswith("/"):
        return None
    parts = value[1:].split("/", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    return parts[0].strip(), parts[1].strip()


def parse_dnsmasq_config(lines: list[str]) -> dict[str, Any]:
    """Parse ArmFirewall-managed dnsmasq settings from dnsmasq.conf."""
    config = default_config()
    known: set[int] = set()
    servers: list[str] = []
    domain_servers: dict[str, list[str]] = {}
    interfaces: list[str] = []
    interface_configs: list[dict[str, Any]] = []
    extras: list[str] = []

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.startswith(DNSMASQ_INTERFACE_CONFIG_PREFIX):
            try:
                parsed = json.loads(line.removeprefix(DNSMASQ_INTERFACE_CONFIG_PREFIX).strip())
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("iface"):
                interface_configs.append(parsed)
            known.add(index)
            continue
        if line.startswith("# armfirewall-listen-all-interfaces="):
            if line.split("=", 1)[1].strip() == "1":
                interfaces = [DNSMASQ_ALL_INTERFACES_TOKEN]
            known.add(index)
            continue
        if line.startswith("# armfirewall-adguardhome-upstream="):
            config["adguardhome_upstream_enabled"] = line.split("=", 1)[1].strip() == "1"
            known.add(index)
            continue
        if not line or line.startswith("#"):
            known.add(index)
            continue
        if line == "bind-interfaces":
            known.add(index)
            continue
        if line == "expand-hosts":
            config["expand_hosts"] = True
            known.add(index)
            continue
        if line == "domain-needed":
            config["domain_needed"] = True
            known.add(index)
            continue
        if line == "bogus-priv":
            config["bogus_priv"] = True
            known.add(index)
            continue
        if line == "dhcp-authoritative":
            config["dhcp_authoritative"] = True
            known.add(index)
            continue
        if line.startswith("port="):
            config["dns_enabled"] = line.split("=", 1)[1].strip() != "0"
            known.add(index)
            continue
        if line.startswith("interface="):
            interfaces.append(line.split("=", 1)[1].strip())
            known.add(index)
            continue
        if line.startswith("domain="):
            config["local_domain"] = line.split("=", 1)[1].strip()
            known.add(index)
            continue
        if line.startswith("local=/"):
            known.add(index)
            continue
        if line.startswith("server="):
            server_value = line.split("=", 1)[1].strip()
            domain_server = parse_domain_server(server_value)
            if domain_server:
                domain, upstream = domain_server
                domain_servers.setdefault(domain, []).append(upstream)
            else:
                servers.append(server_value)
            known.add(index)
            continue
        if line.startswith("cache-size="):
            config["cache_size"] = line.split("=", 1)[1].strip()
            known.add(index)
            continue
        if line.startswith("dhcp-range="):
            parts = split_csv(line.split("=", 1)[1])
            config["dhcp_enabled"] = True
            config["dhcp_range_start"] = parts[0] if len(parts) > 0 else ""
            config["dhcp_range_end"] = parts[1] if len(parts) > 1 else ""
            config["lease_time"] = parts[2] if len(parts) > 2 else config["lease_time"]
            known.add(index)
            continue

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if index not in known and line:
            extras.append(raw_line)

    if interfaces:
        config["listen_interfaces"] = interfaces
    if servers:
        config["upstream_dns_servers"] = servers
    if domain_servers:
        config["domain_upstreams"] = [
            {"domain": domain, "upstreams": upstreams}
            for domain, upstreams in sorted(domain_servers.items())
        ]
    if interface_configs:
        config["interface_configs"] = interface_configs
    elif interfaces:
        config["interface_configs"] = [interface_config_from_global(iface_name, config) for iface_name in interfaces]
    config["extra_options"] = "\n".join(extras)
    return config


def render_config(config: dict[str, Any]) -> str:
    """Render normalized settings as dnsmasq.conf content."""
    interface_configs = config.get("interface_configs") or [
        interface_config_from_global(iface_name, config)
        for iface_name in config.get("listen_interfaces", [])
        if iface_name != DNSMASQ_ALL_INTERFACES_TOKEN
    ]
    has_listen_scope = bool(config.get("listen_interfaces"))
    dns_enabled = bool(config["dns_enabled"]) and has_listen_scope
    dhcp_enabled = any(item["dhcp_enabled"] for item in interface_configs) or bool(config["dhcp_enabled"])
    ipv6_ra_enabled = any(item["ipv6_ra_enabled"] for item in interface_configs)
    lines = [
        "# ArmFirewall managed dnsmasq configuration.",
        "# Generated from Services / Dnsmasq.",
        f"# armfirewall-adguardhome-upstream={1 if config['adguardhome_upstream_enabled'] else 0}",
        f"port={DNSMASQ_DNS_PORT if dns_enabled else 0}",
        "bind-interfaces",
    ]

    if ipv6_ra_enabled:
        lines.append("enable-ra")

    if dhcp_enabled:
        lines.append(f"dhcp-leasefile={DNSMASQ_LEASES_PATH}")
        for static_lease in config.get("static_leases", []):
            lines.append(f"dhcp-host={static_lease['mac_address']},{static_lease['ip_address']}")

    if DNSMASQ_ALL_INTERFACES_TOKEN in config["listen_interfaces"]:
        lines.append("# armfirewall-listen-all-interfaces=1")
    else:
        lines.append("# armfirewall-listen-all-interfaces=0")
        for iface_name in config["listen_interfaces"]:
            lines.append(f"interface={iface_name}")

    rendered_domains: set[str] = set()
    rendered_locals: set[str] = set()
    rendered_servers: set[str] = set()
    rendered_directives: set[str] = set()
    rendered_ranges: set[str] = set()

    if dns_enabled:
        domain = config["local_domain"]
        lines.append(f"domain={domain}")
        lines.append(f"local=/{domain}/")
        lines.append(f"cache-size={config['cache_size']}")
        for enabled, directive in (
            (config["expand_hosts"], "expand-hosts"),
            (config["domain_needed"], "domain-needed"),
            (config["bogus_priv"], "bogus-priv"),
        ):
            if enabled:
                lines.append(directive)
        for server in config["upstream_dns_servers"]:
            lines.append(f"server={server}")
        for domain_item in config["domain_upstreams"]:
            for server in domain_item["upstreams"]:
                lines.append(f"server=/{domain_item['domain']}/{server}")

    for item in interface_configs:
        if item["dhcp_enabled"]:
            range_line = (
                f"dhcp-range=tag:{item['iface']},"
                f"{item['dhcp_range_start']},{item['dhcp_range_end']},{item['lease_time']}"
            )
            if range_line not in rendered_ranges:
                lines.append(f"# DHCP scope for {item['iface']}")
                lines.append(range_line)
                rendered_ranges.add(range_line)
            if item["dhcp_authoritative"] and "dhcp-authoritative" not in rendered_directives:
                lines.append("dhcp-authoritative")
                rendered_directives.add("dhcp-authoritative")
        if item["ipv6_ra_enabled"]:
            options = ["ra-stateless"]
            if item["ipv6_ra_names"]:
                options.append("ra-names")
            lines.append(f"# IPv6 Router Advertisement for {item['iface']}")
            lines.append(
                f"dhcp-range=::1,constructor:{item['iface']},"
                f"{','.join(options)},{item['ipv6_ra_lifetime']}"
            )

    if config["extra_options"]:
        lines.append("")
        lines.append("# Extra options")
        lines.extend(line.rstrip() for line in config["extra_options"].splitlines() if line.strip() and line.strip() != "-")

    return "\n".join(lines).rstrip() + "\n"


def validate_dnsmasq_syntax(config_text: str) -> tuple[bool, str]:
    """Validate generated dnsmasq config when dnsmasq is installed."""
    dnsmasq = shutil.which("dnsmasq")
    if not dnsmasq:
        return True, "dnsmasq binary was not found; syntax validation skipped."

    tmp_path = DNSMASQ_CONF_PATH.with_suffix(".conf.check")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(config_text, encoding="utf-8")
    result = subprocess.run(
        [dnsmasq, "--test", f"--conf-file={tmp_path}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        match = re.search(r"line\s+(\d+)", output)
        if match:
            line_number = int(match.group(1))
            lines = config_text.splitlines()
            if 1 <= line_number <= len(lines):
                output = f"{output}: {lines[line_number - 1]}"
        return False, output or "dnsmasq syntax check failed."
    tmp_path.unlink(missing_ok=True)
    return result.returncode == 0, output or "dnsmasq syntax check completed."
