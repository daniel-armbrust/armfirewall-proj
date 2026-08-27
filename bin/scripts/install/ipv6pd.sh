#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

PD_HINT="${IPV6_PD_HINT:-::/56}"
PD_SUBNET_ID="${IPV6_PD_SUBNET_ID:-0}"

router_mode_enabled() {
    [[ "${ROUTER_MODE:-0}" == "1" ]]
}

connection_for_interface() {
    local iface="$1"
    local connection

    connection="$(nmcli -g GENERAL.CONNECTION device show "$iface" 2>/dev/null || true)"
    [[ -n "$connection" && "$connection" != "--" ]] || fatal "No active NetworkManager connection was found for ${iface}."
    printf '%s\n' "$connection"
}

networkmanager_supports_prefix_delegation() {
    local version major minor

    version="$(nmcli --version | awk 'NR == 1 { print $NF }')"
    IFS=. read -r major minor _ <<<"$version"
    [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] || return 1
    (( major > 1 || (major == 1 && minor >= 54) ))
}

validate_settings() {
    [[ -n "${WAN_IFACE:-}" ]] || fatal "IPv6 prefix delegation requires WAN_IFACE."
    [[ -n "${LAN_IFACE:-}" ]] || fatal "IPv6 prefix delegation requires LAN_IFACE."
    [[ "$WAN_IFACE" != "$LAN_IFACE" ]] || fatal "IPv6 prefix delegation requires different WAN and LAN interfaces."
    [[ "$PD_HINT" =~ ^::/[0-9]{1,3}$ ]] || fatal "IPV6_PD_HINT must be an IPv6 prefix-length hint such as ::/56."
    local pd_length="${PD_HINT#::/}"
    (( 48 <= 10#$pd_length && 10#$pd_length <= 64 )) || fatal "IPV6_PD_HINT must request a prefix between /48 and /64."
    [[ "$PD_SUBNET_ID" =~ ^[0-9]+$ ]] || fatal "IPV6_PD_SUBNET_ID must be a non-negative integer."
    has_cmd nmcli || fatal "NetworkManager (nmcli) is required for IPv6 prefix delegation."
}

configure_ipv6_prefix_delegation() {
    local wan_connection lan_connection

    router_mode_enabled || return 0
    validate_settings

    wan_connection="$(connection_for_interface "$WAN_IFACE")"
    lan_connection="$(connection_for_interface "$LAN_IFACE")"
    networkmanager_supports_prefix_delegation || fatal \
        "NetworkManager 1.54 or newer is required for IPv6 prefix delegation; upgrade NetworkManager before enabling router mode."

    log "Requesting IPv6 prefix delegation (${PD_HINT}) through ${WAN_IFACE}."
    nmcli connection modify "$wan_connection" \
        ipv6.method auto \
        ipv6.dhcp-pd-hint "$PD_HINT" \
        ipv6.forwarding yes

    log "Assigning delegated IPv6 subnet ${PD_SUBNET_ID} to ${LAN_IFACE}."
    nmcli connection modify "$lan_connection" \
        ipv6.method auto \
        ipv6.never-default yes \
        ipv6.forwarding yes \
        prefix-delegation.subnet-id "$PD_SUBNET_ID"

    # Reapply instead of cycling the connections: this preserves the active
    # management path while making NetworkManager request/assign the prefix.
    nmcli device reapply "$WAN_IFACE"
    nmcli device reapply "$LAN_IFACE"
}

configure_ipv6_prefix_delegation
