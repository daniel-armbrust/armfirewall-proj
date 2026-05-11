from __future__ import annotations

import ipaddress
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core import iface as iface_module
from web.services import status as service_status


ROOT_DIR = Path(__file__).resolve().parents[3]
DNSMASQ_CONF = ROOT_DIR / "conf" / "dnsmasq.conf"
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])

DOMAIN_RE = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
BOOL_DEFAULTS = {
    "expand_hosts": True,
    "domain_needed": True,
    "bogus_priv": True,
    "dhcp_authoritative": False,
}
ALL_INTERFACES_TOKEN = "__all__"
INTERFACE_CONFIG_PREFIX = "# armfirewall-interface-config="


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for service pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_dnsmasq(request: Request) -> HTMLResponse:
    """Render the Dnsmasq service template."""
    return templates.TemplateResponse(
        request,
        "services/dnsmasq.html",
        context=page_context(request, "Dnsmasq"),
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
        "pihole_upstream_enabled": False,
        "dhcp_range_start": "",
        "dhcp_range_end": "",
        "lease_time": "12h",
        "cache_size": 1000,
        "expand_hosts": BOOL_DEFAULTS["expand_hosts"],
        "domain_needed": BOOL_DEFAULTS["domain_needed"],
        "bogus_priv": BOOL_DEFAULTS["bogus_priv"],
        "dhcp_authoritative": BOOL_DEFAULTS["dhcp_authoritative"],
        "extra_options": "",
    }


def default_interface_config(iface_name: str) -> dict[str, Any]:
    """Return default DNS and DHCP settings for one interface."""
    return {
        "iface": iface_name,
        "dns_enabled": False,
        "local_domain": "armfirewall.local",
        "upstream_dns_servers": ["1.1.1.1", "8.8.8.8"],
        "domain_upstreams": [],
        "pihole_upstream_enabled": False,
        "cache_size": 1000,
        "expand_hosts": BOOL_DEFAULTS["expand_hosts"],
        "domain_needed": BOOL_DEFAULTS["domain_needed"],
        "bogus_priv": BOOL_DEFAULTS["bogus_priv"],
        "dhcp_enabled": False,
        "dhcp_range_start": "",
        "dhcp_range_end": "",
        "lease_time": "12h",
        "dhcp_authoritative": BOOL_DEFAULTS["dhcp_authoritative"],
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
    if not DNSMASQ_CONF.exists():
        return []
    return DNSMASQ_CONF.read_text(encoding="utf-8").splitlines()


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
        if line.startswith(INTERFACE_CONFIG_PREFIX):
            try:
                parsed = json.loads(line.removeprefix(INTERFACE_CONFIG_PREFIX).strip())
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("iface"):
                interface_configs.append(parsed)
            known.add(index)
            continue
        if line.startswith("# armfirewall-listen-all-interfaces="):
            if line.split("=", 1)[1].strip() == "1":
                interfaces = [ALL_INTERFACES_TOKEN]
            known.add(index)
            continue
        if line.startswith("# armfirewall-pihole-upstream="):
            config["pihole_upstream_enabled"] = line.split("=", 1)[1].strip() == "1"
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


def list_interfaces() -> list[dict[str, Any]]:
    """Return available interfaces for dnsmasq binding."""
    try:
        return iface_module.get_interfaces().get("interfaces", [])
    except HTTPException:
        return []


def dnsmasq_version() -> str:
    """Return the installed dnsmasq version when available."""
    dnsmasq = shutil.which("dnsmasq")
    if not dnsmasq:
        return "not installed"
    try:
        result = subprocess.run(
            [dnsmasq, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    output = (result.stdout or result.stderr).strip().splitlines()
    if not output:
        return "unknown"
    match = re.search(r"version\s+([^\s,]+)", output[0], re.IGNORECASE)
    return match.group(1) if match else output[0]


def dnsmasq_status() -> dict[str, Any]:
    """Return supervisor status for armfirewall-dnsmasq."""
    rows = service_status.supervisor_programs()
    row = next((item for item in rows if item["name"] == "armfirewall-dnsmasq"), None)
    return {
        "installed": row is not None,
        "state": row["state"] if row else "NOT INSTALLED",
        "version": dnsmasq_version(),
        "pid": row["pid"] if row else "-",
        "uptime": row["uptime"] if row else "-",
        "details": row["details"] if row else "Missing from supervisord.conf",
    }


def get_dnsmasq_config() -> dict[str, Any]:
    """Return dnsmasq configuration, interfaces, and service state."""
    lines = read_config_lines()
    return {
        "config": parse_dnsmasq_config(lines),
        "interfaces": list_interfaces(),
        "service": dnsmasq_status(),
        "summary": {
            "config_path": str(DNSMASQ_CONF),
            "exists": DNSMASQ_CONF.exists(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


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


def validate_dns_domain(value: Any, field_name: str) -> str:
    """Validate one DNS domain field."""
    domain = str(value or "armfirewall.local").strip().strip(".")
    if not domain or len(domain) > 253 or not DOMAIN_RE.match(domain):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid DNS domain.")
    return domain


def validate_domain(value: Any) -> str:
    """Validate the local DNS domain."""
    return validate_dns_domain(value, "local_domain")


def validate_interfaces(values: Any) -> list[str]:
    """Validate requested listen interfaces."""
    requested = [str(item).strip() for item in values or [] if str(item).strip()]
    if ALL_INTERFACES_TOKEN in requested:
        return [ALL_INTERFACES_TOKEN]
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
    config["dns_enabled"] = bool(item.get("dns_enabled"))
    config["local_domain"] = validate_domain(item.get("local_domain"))
    config["upstream_dns_servers"] = normalize_upstream_list(item.get("upstream_dns_servers"), f"{iface_name}.upstream_dns_servers")
    config["pihole_upstream_enabled"] = bool(item.get("pihole_upstream_enabled"))
    config["domain_upstreams"] = [] if config["pihole_upstream_enabled"] else validate_domain_upstreams(item.get("domain_upstreams"))
    config["cache_size"] = validate_cache_size(item.get("cache_size", config["cache_size"]))
    config["expand_hosts"] = bool(item.get("expand_hosts"))
    config["domain_needed"] = bool(item.get("domain_needed"))
    config["bogus_priv"] = bool(item.get("bogus_priv"))
    config["dhcp_enabled"] = bool(item.get("dhcp_enabled"))
    config["dhcp_range_start"] = validate_optional_ip(item.get("dhcp_range_start"), f"{iface_name}.dhcp_range_start")
    config["dhcp_range_end"] = validate_optional_ip(item.get("dhcp_range_end"), f"{iface_name}.dhcp_range_end")
    config["lease_time"] = validate_lease_time(item.get("lease_time"))
    config["dhcp_authoritative"] = bool(item.get("dhcp_authoritative"))

    if config["dns_enabled"] and not config["pihole_upstream_enabled"] and not config["upstream_dns_servers"]:
        raise HTTPException(status_code=400, detail=f"At least one upstream DNS server is required for {iface_name}.")
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
        return [interface_config_from_global(iface_name, fallback) for iface_name in fallback["listen_interfaces"] if iface_name != ALL_INTERFACES_TOKEN]
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
    config["pihole_upstream_enabled"] = bool(payload.get("pihole_upstream_enabled"))
    config["dhcp_range_start"] = validate_optional_ip(payload.get("dhcp_range_start"), "dhcp_range_start")
    config["dhcp_range_end"] = validate_optional_ip(payload.get("dhcp_range_end"), "dhcp_range_end")
    config["lease_time"] = validate_lease_time(payload.get("lease_time"))
    config["cache_size"] = validate_cache_size(payload.get("cache_size", config["cache_size"]))
    config["expand_hosts"] = bool(payload.get("expand_hosts"))
    config["domain_needed"] = bool(payload.get("domain_needed"))
    config["bogus_priv"] = bool(payload.get("bogus_priv"))
    config["dhcp_authoritative"] = bool(payload.get("dhcp_authoritative"))
    config["extra_options"] = str(payload.get("extra_options") or "").strip()

    if has_interface_configs:
        config["interface_configs"] = normalize_interface_configs(payload.get("interface_configs"), config)
        config["listen_interfaces"] = [item["iface"] for item in config["interface_configs"]]
        first = config["interface_configs"][0] if config["interface_configs"] else default_interface_config("")
        for key in (
            "local_domain",
            "upstream_dns_servers",
            "domain_upstreams",
            "pihole_upstream_enabled",
            "cache_size",
            "expand_hosts",
            "domain_needed",
            "bogus_priv",
            "dhcp_range_start",
            "dhcp_range_end",
            "lease_time",
            "dhcp_authoritative",
        ):
            config[key] = first[key]
        config["dns_enabled"] = any(item["dns_enabled"] for item in config["interface_configs"])
        config["dhcp_enabled"] = any(item["dhcp_enabled"] for item in config["interface_configs"])
        return config

    if config["dns_enabled"] and not config["pihole_upstream_enabled"] and not config["upstream_dns_servers"]:
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


def render_config(config: dict[str, Any]) -> str:
    """Render normalized settings as dnsmasq.conf content."""
    interface_configs = config.get("interface_configs") or [
        interface_config_from_global(iface_name, config)
        for iface_name in config.get("listen_interfaces", [])
        if iface_name != ALL_INTERFACES_TOKEN
    ]
    dns_enabled = any(item["dns_enabled"] for item in interface_configs) or bool(config["dns_enabled"])
    dhcp_enabled = any(item["dhcp_enabled"] for item in interface_configs) or bool(config["dhcp_enabled"])
    lines = [
        "# ArmFirewall managed dnsmasq configuration.",
        "# Generated from Services / Dnsmasq.",
        f"port={53 if dns_enabled else 0}",
        "bind-interfaces",
    ]

    if ALL_INTERFACES_TOKEN in config["listen_interfaces"]:
        lines.append("# armfirewall-listen-all-interfaces=1")
    else:
        lines.append("# armfirewall-listen-all-interfaces=0")
        for iface_name in config["listen_interfaces"]:
            lines.append(f"interface={iface_name}")

    for item in interface_configs:
        lines.append(f"{INTERFACE_CONFIG_PREFIX}{json.dumps(item, sort_keys=True, separators=(',', ':'))}")

    rendered_domains: set[str] = set()
    rendered_locals: set[str] = set()
    rendered_servers: set[str] = set()
    rendered_directives: set[str] = set()
    rendered_ranges: set[str] = set()

    for item in interface_configs:
        if item["dns_enabled"]:
            domain = item["local_domain"]
            if domain not in rendered_domains:
                lines.append(f"domain={domain}")
                rendered_domains.add(domain)
            local_line = f"local=/{domain}/"
            if local_line not in rendered_locals:
                lines.append(local_line)
                rendered_locals.add(local_line)
            cache_line = f"cache-size={item['cache_size']}"
            if cache_line not in rendered_directives:
                lines.append(cache_line)
                rendered_directives.add(cache_line)
            for enabled, directive in (
                (item["expand_hosts"], "expand-hosts"),
                (item["domain_needed"], "domain-needed"),
                (item["bogus_priv"], "bogus-priv"),
            ):
                if enabled and directive not in rendered_directives:
                    lines.append(directive)
                    rendered_directives.add(directive)
            if item["pihole_upstream_enabled"]:
                marker = f"# armfirewall-pihole-upstream-{item['iface']}=1"
                lines.append(marker)
            else:
                marker = f"# armfirewall-pihole-upstream-{item['iface']}=0"
                lines.append(marker)
                for server in item["upstream_dns_servers"]:
                    server_line = f"server={server}"
                    if server_line not in rendered_servers:
                        lines.append(server_line)
                        rendered_servers.add(server_line)
            for domain_item in item["domain_upstreams"]:
                for server in domain_item["upstreams"]:
                    server_line = f"server=/{domain_item['domain']}/{server}"
                    if server_line not in rendered_servers:
                        lines.append(server_line)
                        rendered_servers.add(server_line)

        if item["dhcp_enabled"]:
            range_line = f"dhcp-range={item['dhcp_range_start']},{item['dhcp_range_end']},{item['lease_time']}"
            if range_line not in rendered_ranges:
                lines.append(range_line)
                rendered_ranges.add(range_line)
            if item["dhcp_authoritative"] and "dhcp-authoritative" not in rendered_directives:
                lines.append("dhcp-authoritative")
                rendered_directives.add("dhcp-authoritative")

    if not interface_configs:
        lines.append(f"# armfirewall-pihole-upstream={'1' if config['pihole_upstream_enabled'] else '0'}")

    if config["extra_options"]:
        lines.append("")
        lines.append("# Extra options")
        lines.extend(line.rstrip() for line in config["extra_options"].splitlines() if line.strip())

    return "\n".join(lines).rstrip() + "\n"


def validate_dnsmasq_syntax(config_text: str) -> tuple[bool, str]:
    """Validate generated dnsmasq config when dnsmasq is installed."""
    dnsmasq = shutil.which("dnsmasq")
    if not dnsmasq:
        return True, "dnsmasq binary was not found; syntax validation skipped."

    tmp_path = DNSMASQ_CONF.with_suffix(".conf.check")
    tmp_path.write_text(config_text, encoding="utf-8")
    try:
        result = subprocess.run(
            [dnsmasq, "--test", f"--conf-file={tmp_path}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output or "dnsmasq syntax check completed."


def save_dnsmasq_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and save dnsmasq.conf from the GUI."""
    config = normalize_config(payload)
    config_text = render_config(config)
    ok, message = validate_dnsmasq_syntax(config_text)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    DNSMASQ_CONF.parent.mkdir(parents=True, exist_ok=True)
    DNSMASQ_CONF.write_text(config_text, encoding="utf-8")
    return {
        "saved": True,
        "message": message,
        "config": parse_dnsmasq_config(config_text.splitlines()),
        "summary": {
            "config_path": str(DNSMASQ_CONF),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def test_dnsmasq_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate either posted settings or the current dnsmasq.conf."""
    if payload:
        config_text = render_config(normalize_config(payload))
    else:
        config_text = DNSMASQ_CONF.read_text(encoding="utf-8") if DNSMASQ_CONF.exists() else render_config(default_config())

    ok, message = validate_dnsmasq_syntax(config_text)
    return {"ok": ok, "message": message}
