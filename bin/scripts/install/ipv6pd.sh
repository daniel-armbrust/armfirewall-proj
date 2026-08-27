#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

PD_HINT="${IPV6_PD_HINT:-::/56}"
PD_SUBNET_ID="${IPV6_PD_SUBNET_ID:-0}"
NETWORKMANAGER_MIN_VERSION="${NETWORKMANAGER_MIN_VERSION:-1.54}"

router_mode_enabled() {
    [[ "${ROUTER_MODE:-0}" == "1" ]]
}

# Return the UUID of an active NetworkManager connection for an interface.
active_connection_uuid() {
    local iface="$1"
    local uuid

    uuid="$(nmcli -g GENERAL.CON-UUID device show "$iface" 2>/dev/null | head -n 1 || true)"
    [[ -n "$uuid" && "$uuid" != "--" ]] && printf '%s\n' "$uuid"
}

# Return one persisted NetworkManager connection UUID bound to an interface.
connection_uuid_for_interface() {
    local iface="$1" uuid profile_iface

    uuid="$(active_connection_uuid "$iface" || true)"
    [[ -n "$uuid" ]] && {
        printf '%s\n' "$uuid"
        return 0
    }

    while IFS= read -r uuid; do
        [[ -n "$uuid" ]] || continue
        profile_iface="$(nmcli -g connection.interface-name connection show uuid "$uuid" 2>/dev/null | head -n 1 || true)"
        [[ "$profile_iface" == "$iface" ]] && {
            printf '%s\n' "$uuid"
            return 0
        }
    done < <(nmcli -g UUID connection show 2>/dev/null || true)

    fatal "No NetworkManager connection profile was found for ${iface}."
}

# Reapply a device only when it has an active NetworkManager connection.
reapply_active_device() {
    local iface="$1"

    if active_connection_uuid "$iface" >/dev/null; then
        nmcli device reapply "$iface"
    else
        log "Saved IPv6 prefix delegation configuration for ${iface}; it will apply when the connection becomes active."
    fi
}

networkmanager_supports_prefix_delegation() {
    local version major minor

    version="$(nmcli --version | awk 'NR == 1 { print $NF }')"
    IFS=. read -r major minor _ <<<"$version"
    [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] || return 1
    local required_major required_minor
    IFS=. read -r required_major required_minor _ <<<"$NETWORKMANAGER_MIN_VERSION"
    [[ "$required_major" =~ ^[0-9]+$ && "$required_minor" =~ ^[0-9]+$ ]] || return 1
    (( major > required_major || (major == required_major && minor >= required_minor) ))
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

    wan_connection="$(active_connection_uuid "$WAN_IFACE" || true)"
    [[ -n "$wan_connection" ]] || fatal "No active NetworkManager connection was found for ${WAN_IFACE}."
    lan_connection="$(connection_uuid_for_interface "$LAN_IFACE")"
    networkmanager_supports_prefix_delegation || fatal \
        "NetworkManager ${NETWORKMANAGER_MIN_VERSION} or newer is required for IPv6 prefix delegation; upgrade NetworkManager before enabling router mode."

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
    reapply_active_device "$WAN_IFACE"
    reapply_active_device "$LAN_IFACE"
}

configure_ipv6_prefix_delegation
