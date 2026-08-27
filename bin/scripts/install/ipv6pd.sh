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
    local wan_connection lan_connection
    has_cmd nmcli || return 0
    wan_connection="$(active_connection_uuid "$WAN_IFACE" || true)"
    lan_connection="$(active_connection_uuid "$LAN_IFACE" || true)"
    [[ -n "$wan_connection" ]] && nmcli connection modify "$wan_connection" ipv6.method disabled
    [[ -n "$lan_connection" ]] && nmcli connection modify "$lan_connection" ipv6.method disabled
    [[ -n "$wan_connection" ]] && nmcli device reapply "$WAN_IFACE" || true
    [[ -n "$lan_connection" ]] && nmcli device reapply "$LAN_IFACE" || true
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
noipv6rs
allowinterfaces $WAN_IFACE $LAN_IFACE
interface $WAN_IFACE
ia_pd 1 $LAN_IFACE/$PD_SUBNET_ID/64/1
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
        install_legacy_pd_service
    fi
}

main "$@"
