#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

provision_dnsmasq() {
    local lan_iface="$1"
    local lan_ipv4_addr="$2"

    (
        cd "$ROOT_DIR"
        "$ROOT_DIR/.venv/bin/python" - "$lan_iface" "$lan_ipv4_addr" <<'PY'
import ipaddress
import json
import sys

from core import db
from core.constants import DNSMASQ_CONF_PATH, DNSMASQ_DB_PATH, DNSMASQ_LEASES_PATH, SERVICES_DB_PATH
from daemons.dnsmasq.dns_routing import ensure_lan_dns_redirect_rules
from web.services.dnsmasq.configuration import (
    default_config,
    default_interface_config,
    render_config,
    validate_dnsmasq_syntax,
)

iface, address_spec = sys.argv[1:]
upstreams = ["8.8.8.8", "1.1.1.1"]

config = default_config()
config.update(
    dns_enabled=True,
    dhcp_enabled=False,
    listen_interfaces=[iface],
    upstream_dns_servers=upstreams,
    interface_configs=[],
)
interface_config = default_interface_config(iface)
interface_config.update(
    dns_enabled=True,
    upstream_dns_servers=upstreams,
    dhcp_enabled=False,
    dhcp_authoritative=True,
    ipv6_ra_enabled=True,
    ipv6_ra_names=True,
    ipv6_ra_lifetime="4h",
)

if address_spec != "dhcp":
    interface = ipaddress.IPv4Interface(address_spec)
    network = interface.network
    if network.prefixlen > 29:
        raise RuntimeError(
            f"LAN network {network} is too small for five reserved addresses and DHCP."
        )

    first_host = int(network.network_address) + 1
    last_host = int(network.broadcast_address) - 1
    reserved_last = min(first_host + 4, last_host)
    router_address = int(interface.ip)
    free = [
        address
        for address in range(first_host, last_host + 1)
        if address > reserved_last and address != router_address
    ]
    if not free:
        raise RuntimeError(f"LAN network {network} has no free DHCP addresses.")

    ranges: list[list[int]] = []
    current: list[int] = []
    previous: int | None = None
    for address in free:
        if previous is None or address == previous + 1:
            current.append(address)
        else:
            ranges.append(current)
            current = [address]
        previous = address
    ranges.append(current)

    # dnsmasq's stored interface scope is one contiguous range. With the normal
    # gateway-at-first-host topology, this yields 90% of all free addresses.
    desired = max(1, (len(free) * 90) // 100)
    pool = max(ranges, key=len)[:desired]
    if not pool:
        raise RuntimeError(f"LAN network {network} has no contiguous DHCP scope.")

    interface_config.update(
        dhcp_enabled=True,
        dhcp_range_start=str(ipaddress.IPv4Address(pool[0])),
        dhcp_range_end=str(ipaddress.IPv4Address(pool[-1])),
    )
    config["extra_options"] = (
        f"dhcp-option=tag:{iface},option:router,{interface.ip}"
    )
    config["dhcp_enabled"] = True

config["interface_configs"] = [interface_config]
config_text = render_config(config)
ok, message = validate_dnsmasq_syntax(config_text)
if not ok:
    raise RuntimeError(message)

with db.transaction(DNSMASQ_DB_PATH) as conn:
    db.execute_on(
        conn,
        """
        UPDATE dnsmasq_settings
           SET dns_enabled = 1,
               local_domain = ?,
               upstream_dns_servers_json = ?,
               cache_size = ?,
               expand_hosts = ?,
               domain_needed = ?,
               bogus_priv = ?,
               extra_options = ?,
               pending_apply = 0,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = 1
        """,
        (
            config["local_domain"],
            json.dumps(upstreams),
            config["cache_size"],
            int(config["expand_hosts"]),
            int(config["domain_needed"]),
            int(config["bogus_priv"]),
            config["extra_options"],
        ),
    )
    db.execute_on(conn, "DELETE FROM dnsmasq_global_domain_upstreams")
    db.execute_on(conn, "DELETE FROM dnsmasq_interface_configs")
    db.execute_on(
        conn,
        """
        INSERT INTO dnsmasq_interface_configs (
            iface, dns_enabled, local_domain, upstream_dns_servers_json,
            cache_size, expand_hosts, domain_needed,
            bogus_priv, dhcp_enabled, dhcp_range_start, dhcp_range_end,
            lease_time, dhcp_authoritative, ipv6_ra_enabled,
            ipv6_ra_names, ipv6_ra_lifetime, enabled
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            iface,
            interface_config["local_domain"],
            json.dumps(upstreams),
            interface_config["cache_size"],
            int(interface_config["expand_hosts"]),
            int(interface_config["domain_needed"]),
            int(interface_config["bogus_priv"]),
            int(interface_config["dhcp_enabled"]),
            interface_config["dhcp_range_start"],
            interface_config["dhcp_range_end"],
            interface_config["lease_time"],
            int(interface_config["dhcp_authoritative"]),
            int(interface_config["ipv6_ra_enabled"]),
            int(interface_config["ipv6_ra_names"]),
            interface_config["ipv6_ra_lifetime"],
        ),
    )

with db.transaction(SERVICES_DB_PATH) as conn:
    db.execute_on(
        conn,
        """
        UPDATE services
           SET runtime_installed = 1,
               autostart_enabled = 1,
               enabled = 1,
               updated_at = CURRENT_TIMESTAMP
         WHERE name = 'dnsmasq'
        """,
    )

DNSMASQ_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
DNSMASQ_LEASES_PATH.parent.mkdir(parents=True, exist_ok=True)
DNSMASQ_LEASES_PATH.touch(exist_ok=True)
DNSMASQ_CONF_PATH.write_text(config_text, encoding="utf-8")
ensure_lan_dns_redirect_rules()

print(
    "DNSMasq provisioned for "
    f"{iface}; DHCP pool {interface_config['dhcp_range_start'] or 'not configured'}"
    f" - {interface_config['dhcp_range_end'] or 'not configured'}."
)
PY
    )

    if [[ "$lan_ipv4_addr" == "dhcp" ]]; then
        log "DNSMasq DNS and IPv6 RA enabled for $lan_iface; DHCP scope skipped because the LAN address uses DHCP."
    else
        log "DNSMasq DNS, DHCP and IPv6 RA provisioned for $lan_iface; the first five usable IPv4 addresses are reserved."
    fi
}

activate_dnsmasq() {
    (
        cd "$ROOT_DIR"
        "$ROOT_DIR/.venv/bin/python" - <<'PY'
from daemons.dnsmasq.resolver import configure_system_resolver
from daemons.svcmgmtd.catalog import optional_service_for_daemon, set_service_autostart_enabled
from daemons.svcmgmtd.models import OptionalService
from daemons.svcmgmtd.supervisor import (
    register_supervisor_program,
    reread_and_update,
    set_supervisor_program_autostart,
    supervisor_command,
    supervisor_status,
)

metadata = optional_service_for_daemon("dnsmasq")
if metadata is None:
    raise RuntimeError("DNSMasq service metadata was not found.")
service = OptionalService(
    name="dnsmasq",
    package=str(metadata["package"]),
    binary=str(metadata["binary"]),
    supervisor_program=str(metadata["supervisor_program"]),
)
register_supervisor_program(service)
set_supervisor_program_autostart("dnsmasq", True)
set_service_autostart_enabled("dnsmasq", True)
reread_and_update()

if supervisor_status("dnsmasq") != "RUNNING":
    supervisor_command("start", "dnsmasq", timeout=60)
if supervisor_status("dnsmasq") != "RUNNING":
    raise RuntimeError("DNSMasq did not start after LAN network configuration.")
configure_system_resolver(True)
PY
    )
    log "DNSMasq is running and configured as the local system resolver."
}

main() {
    if [[ "${1:-}" == "--activate" ]]; then
        activate_dnsmasq
        return
    fi

    [[ "$#" -eq 2 ]] || fatal "Usage: dnsmasq.sh <lan-iface> <lan-ipv4-addr>"
    provision_dnsmasq "$1" "$2"
}

main "$@"
