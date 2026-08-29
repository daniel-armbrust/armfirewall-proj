#!/usr/bin/env bash
set -Eeuo pipefail

# Runs immediately before the legacy dhcpcd IPv6-PD client. NetworkManager
# may receive Router Advertisements before supervisord starts; remove only
# that transient state so a disconnected secondary interface cannot retain a
# lower-metric default route than the primary WAN.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
. "$ROOT_DIR/bin/scripts/common/globals.sh"

DHCPCD_BIN="${1:?dhcpcd path is required}"
DHCPCD_CONF="${2:?dhcpcd configuration path is required}"
WAN_IFACE="${3:?WAN interface is required}"
LAN_IFACE="${4:?LAN interface is required}"

networkmanager_ethernet_interfaces() {
    local iface device_type

    if has_cmd nmcli; then
        while IFS=: read -r iface device_type; do
            [[ -n "$iface" && "$iface" != "lo" && "$device_type" == "ethernet" ]] || continue
            printf '%s\n' "$iface"
        done < <(nmcli -t -f DEVICE,TYPE device status)
        return
    fi

    for iface in /sys/class/net/*; do
        iface="${iface##*/}"
        [[ "$iface" != "lo" ]] && printf '%s\n' "$iface"
    done
}

clear_router_advertisement_state() {
    local iface address

    while IFS= read -r iface; do
        [[ -n "$iface" && -d "/proc/sys/net/ipv6/conf/${iface}" ]] || continue
        ip -6 route flush dev "$iface" proto ra 2>/dev/null || true
        while IFS= read -r address; do
            [[ -n "$address" ]] || continue
            ip -6 address del "$address" dev "$iface" 2>/dev/null || true
        done < <(ip -6 -o address show dev "$iface" scope global dynamic 2>/dev/null | awk '{print $4}')
    done < <(
        {
            printf '%s\n' "$WAN_IFACE" "$LAN_IFACE"
            networkmanager_ethernet_interfaces
        } | awk 'NF && !seen[$0]++'
    )
}

# Desired /proc values are stored in proc.db by the installer. Apply them on
# every boot before clearing state and starting dhcpcd; never write sysctl.d.
"$ROOT_DIR/bin/scripts/startpre/proc.sh"
clear_router_advertisement_state
exec "$DHCPCD_BIN" -6 -B -f "$DHCPCD_CONF" "$WAN_IFACE" "$LAN_IFACE"
