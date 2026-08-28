#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
. "$ROOT_DIR/bin/scripts/common/globals.sh"

PD_HINT="${IPV6_PD_HINT:-::/56}"
PD_SUBNET_ID="${IPV6_PD_SUBNET_ID:-0}"
PD_RUNTIME_DIR="/run/armfirewall/ipv6pd"
PD_SERVICE_CONF="$CONF_DIR/supervisor.d/ipv6pd.ini"
PD_DHCPCD_CONF="$CONF_DIR/ipv6pd-dhcpcd.conf"

uses_dynamic_ipv6() { [[ "${1:-}" == "auto" || "${1:-}" == "dhcp" ]]; }

pd_requested() {
    [[ "${ROUTER_MODE:-0}" == "1" ]] && uses_dynamic_ipv6 "${WAN_IPV6_ADDR:-}" && uses_dynamic_ipv6 "${LAN_IPV6_ADDR:-}"
}

networkmanager_version_supports_pd() {
    local version major minor
    has_cmd nmcli || return 1
    version="$(nmcli --version | awk 'NR == 1 { print $NF }')"
    IFS=. read -r major minor _ <<<"$version"
    [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] || return 1
    (( major > 1 || (major == 1 && minor >= 54) ))
}

active_connection_uuid() {
    local uuid
    uuid="$(nmcli -g GENERAL.CON-UUID device show "$1" 2>/dev/null | head -n1 || true)"
    [[ -n "$uuid" && "$uuid" != "--" ]] && printf '%s\n' "$uuid"
}

# List every persisted Ethernet profile. In the legacy fallback, dhcpcd must
# be the sole IPv6 client on the host. NetworkManager must leave IPv6 to
# dhcpcd rather than disable it: disabling IPv6 prevents the WAN from
# receiving global IPv6 configuration from Router Advertisements.
networkmanager_ethernet_connection_uuids() {
    local uuid connection_type

    while IFS=: read -r uuid connection_type; do
        [[ -n "$uuid" && "$connection_type" == "802-3-ethernet" ]] || continue
        printf '%s\n' "$uuid"
    done < <(nmcli -t -f UUID,TYPE connection show)
}

# List active NetworkManager-controlled Ethernet devices. These are reactivated
# after their profiles are changed so NetworkManager releases any DHCPv6 socket.
networkmanager_active_ethernet_interfaces() {
    local iface device_type
    has_cmd nmcli || return 0

    while IFS=: read -r iface device_type; do
        [[ -n "$iface" && "$iface" != "lo" && "$device_type" == "ethernet" ]] || continue
        printf '%s\n' "$iface"
    done < <(nmcli -t -f DEVICE,TYPE device status)
}

# Reconnect a profile after changing ipv6.method. NetworkManager cannot
# reliably remove an already running DHCPv6 client through device reapply.
reconnect_networkmanager_connection() {
    local iface="$1" connection="$2" state

    state="$(nmcli -g GENERAL.STATE device show "$iface" 2>/dev/null | head -n1 || true)"
    [[ "$state" == 100* ]] || return 0
    nmcli connection up uuid "$connection" ifname "$iface" >/dev/null || \
        fatal "Could not reactivate ${iface} after leaving IPv6 unmanaged by NetworkManager."
}

configure_networkmanager_pd() {
    local wan_connection lan_connection
    wan_connection="$(active_connection_uuid "$WAN_IFACE" || true)"
    lan_connection="$(active_connection_uuid "$LAN_IFACE" || true)"
    [[ -n "$wan_connection" && -n "$lan_connection" ]] || fatal "Active NetworkManager connections are required for IPv6 prefix delegation."
    nmcli connection modify "$wan_connection" ipv6.method auto ipv6.dhcp-pd-hint "$PD_HINT" ipv6.forwarding yes
    nmcli connection modify "$lan_connection" ipv6.method auto ipv6.never-default yes ipv6.forwarding yes prefix-delegation.subnet-id "$PD_SUBNET_ID"
    nmcli device reapply "$WAN_IFACE"
    nmcli device reapply "$LAN_IFACE"
    log "NetworkManager will manage IPv6 prefix delegation."
}

configure_legacy_networkmanager() {
    local iface connection
    has_cmd nmcli || return 0

    while IFS= read -r connection; do
        nmcli connection modify "$connection" \
            ipv6.method ignore ipv6.addresses "" ipv6.gateway "" ipv6.dns "" \
            ipv6.never-default yes ipv6.ignore-auto-routes yes ipv6.ignore-auto-dns yes || \
            fatal "Could not leave IPv6 unmanaged by NetworkManager on connection ${connection}."
    done < <(networkmanager_ethernet_connection_uuids)

    while IFS= read -r iface; do
        connection="$(active_connection_uuid "$iface" || true)"
        [[ -n "$connection" ]] || continue
        reconnect_networkmanager_connection "$iface" "$connection"
    done < <(networkmanager_active_ethernet_interfaces)

    log "Configured NetworkManager to leave IPv6 unmanaged on persisted Ethernet profiles; dhcpcd owns WAN RA/SLAAC and DHCPv6 prefix delegation."
}

# Persist one kernel parameter in proc.db. startpre/proc.sh applies all enabled
# desired values both now and on every boot, keeping /proc as runtime state.
record_legacy_proc_value() {
    local name="$1" proc_path="$2" description="$3" default_value="$4" desired_value="$5"

    sqlite_exec "$PROC_DB" "
        INSERT INTO proc (
            category, name, proc_path, description, default_value,
            current_value, desired_value, protected, enabled, collected_at, updated_at
        ) VALUES (
            'IPv6',
            $(sql_quote "$name"),
            $(sql_quote "$proc_path"),
            $(sql_quote "$description"),
            $(sql_quote "$default_value"),
            $(sql_quote "$desired_value"),
            $(sql_quote "$desired_value"),
            0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT(proc_path) DO UPDATE SET
            current_value = excluded.current_value,
            desired_value = excluded.desired_value,
            enabled = 1,
            collected_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP;
    "
}

# dhcpcd owns Router Advertisements, SLAAC, and DHCPv6 on legacy
# NetworkManager hosts. Keep kernel RA processing disabled on every Ethernet
# interface so a pre-existing NetworkManager connection cannot install an RA
# route before dhcpcd takes ownership of the WAN.
configure_legacy_kernel_ipv6() {
    local iface

    [[ -f "$PROC_DB" ]] || fatal "Kernel parameter database was not found: ${PROC_DB}."

    while IFS= read -r iface; do
        [[ -n "$iface" && -d "/proc/sys/net/ipv6/conf/${iface}" ]] || continue
        record_legacy_proc_value \
            "net.ipv6.conf.${iface}.accept_ra" \
            "/proc/sys/net/ipv6/conf/${iface}/accept_ra" \
            "Disables kernel Router Advertisements; dhcpcd owns WAN IPv6." \
            "0" "0"
        record_legacy_proc_value \
            "net.ipv6.conf.${iface}.autoconf" \
            "/proc/sys/net/ipv6/conf/${iface}/autoconf" \
            "Disables kernel IPv6 SLAAC; dhcpcd owns WAN IPv6." \
            "1" "0"
        record_legacy_proc_value \
            "net.ipv6.conf.${iface}.accept_ra_pinfo" \
            "/proc/sys/net/ipv6/conf/${iface}/accept_ra_pinfo" \
            "Disables kernel IPv6 RA prefix processing; dhcpcd owns WAN IPv6." \
            "1" "0"
        record_legacy_proc_value \
            "net.ipv6.conf.${iface}.accept_ra_defrtr" \
            "/proc/sys/net/ipv6/conf/${iface}/accept_ra_defrtr" \
            "Disables kernel IPv6 RA default-router processing; dhcpcd owns WAN IPv6." \
            "1" "0"
    done < <(
        {
            printf '%s\n' "$WAN_IFACE" "$LAN_IFACE"
            networkmanager_active_ethernet_interfaces
        } | awk 'NF && !seen[$0]++'
    )

    "$ROOT_DIR/bin/scripts/startpre/proc.sh" || \
        fatal "Could not apply persisted IPv6 Router Advertisement settings."
    log "Persisted and applied kernel IPv6 settings that reserve Router Advertisements and SLAAC for dhcpcd."
}

# Connections can be active before the installer reaches this script. Remove
# only dynamic IPv6 state learned from those early Router Advertisements, after
# the persistent proc settings are applied and before dhcpcd starts. Static
# addresses and non-RA routes are intentionally preserved.
clear_legacy_ra_state() {
    local iface address

    while IFS= read -r iface; do
        [[ -n "$iface" ]] || continue
        ip -6 route flush dev "$iface" proto ra 2>/dev/null || true
        while IFS= read -r address; do
            [[ -n "$address" ]] || continue
            ip -6 address del "$address" dev "$iface" 2>/dev/null || true
        done < <(ip -6 -o address show dev "$iface" scope global dynamic 2>/dev/null | awk '{print $4}')
    done < <(
        {
            printf '%s\n' "$WAN_IFACE" "$LAN_IFACE"
            networkmanager_active_ethernet_interfaces
        } | awk 'NF && !seen[$0]++'
    )
    log "Cleared dynamic IPv6 Router Advertisement state before starting dhcpcd."
}

install_legacy_pd_service() {
    local dhcpcd_bin pd_length
    has_cmd dhcpcd || fatal "dhcpcd is required for the IPv6 prefix-delegation fallback."
    dhcpcd_bin="$(command -v dhcpcd)"
    pd_length="${PD_HINT#::/}"
    [[ "$pd_length" =~ ^[0-9]+$ ]] || fatal "IPV6_PD_HINT must have the form ::/56."
    mkdir -p "$PD_RUNTIME_DIR" "$CONF_DIR/supervisor.d"
    cat > "$PD_DHCPCD_CONF" <<CONF
# Managed by ArmFirewall: DHCPv6 prefix delegation for legacy NetworkManager.
allowinterfaces $WAN_IFACE $LAN_IFACE
interface $WAN_IFACE
# dhcpcd owns WAN Router Advertisements, SLAAC, and DHCPv6. NetworkManager
# leaves IPv6 untouched so it does not compete for the DHCPv6 socket.
ipv6rs
# Request both the WAN IPv6 address and a prefix to delegate to LAN with
# distinct non-zero IAIDs, as required for independent DHCPv6 associations.
ia_na 1
ia_pd 2 $LAN_IFACE/$PD_SUBNET_ID/64/1
interface $LAN_IFACE
# LAN is a downstream network. Do not solicit Router Advertisements there.
noipv6rs
CONF
    cat > "$PD_SERVICE_CONF" <<CONF
[program:armfirewall-ipv6pd]
directory=$ROOT_DIR
command=$dhcpcd_bin -6 -B -f $PD_DHCPCD_CONF $WAN_IFACE $LAN_IFACE
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
environment=ARMFW_IPV6PD_WAN="$WAN_IFACE",ARMFW_IPV6PD_LAN="$LAN_IFACE",ARMFW_IPV6PD_DHCPCD_CONF="$PD_DHCPCD_CONF",ARMFW_DHCPCD_BIN="$dhcpcd_bin"
stdout_logfile=$ROOT_DIR/logs/armfirewall-ipv6pd.out.log
stderr_logfile=$ROOT_DIR/logs/armfirewall-ipv6pd.err.log
CONF
    supervisorctl -c "$SUPERVISORD_CONF" reread
    supervisorctl -c "$SUPERVISORD_CONF" update
    log "Installed the dhcpcd IPv6 prefix-delegation service."
}

main() {
    pd_requested || { log "IPv6 prefix delegation was not requested."; return 0; }
    [[ -n "${WAN_IFACE:-}" && -n "${LAN_IFACE:-}" && "$WAN_IFACE" != "$LAN_IFACE" ]] || fatal "IPv6 prefix delegation requires distinct WAN and LAN interfaces."
    if networkmanager_version_supports_pd; then
        configure_networkmanager_pd
    else
        configure_legacy_networkmanager
        configure_legacy_kernel_ipv6
        clear_legacy_ra_state
        install_legacy_pd_service
    fi
}

main "$@"
