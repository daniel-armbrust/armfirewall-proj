#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

NETWORK_INTERFACES_FILE="/etc/network/interfaces"
NETWORK_INTERFACES_DIR="/etc/network/interfaces.d"
ARMFIREWALL_INTERFACES_FILE="${NETWORK_INTERFACES_DIR}/armfirewall"
ARMFIREWALL_HOTPLUG_UNIT="armfirewall-ifup-hotplug.service"
ARMFIREWALL_HOTPLUG_UNIT_FILE="/etc/systemd/system/${ARMFIREWALL_HOTPLUG_UNIT}"

# Return success when an address specification requests DHCP.
uses_dhcp() {
    [[ "${1:-}" == "dhcp" ]]
}

# Return success when an IPv6 address specification requests SLAAC.
uses_ipv6_auto() {
    [[ "${1:-}" == "auto" ]]
}

# Validate an IPv4 address with a CIDR prefix, such as 192.0.2.10/24.
validate_ipv4_cidr() {
    local value="$1"
    local address prefix extra octet
    local -a octets

    IFS=/ read -r address prefix extra <<< "$value"
    
    [[ -n "$address" && -n "$prefix" && -z "$extra" ]] || return 1
    [[ "$prefix" =~ ^[0-9]+$ ]] && (( 10#$prefix <= 32 )) || return 1

    IFS=. read -r -a octets <<< "$address"
    [[ ${#octets[@]} -eq 4 ]] || return 1
    
    for octet in "${octets[@]}"; do
        [[ "$octet" =~ ^[0-9]+$ ]] && (( 10#$octet <= 255 )) || return 1
    done
}

# Validate an IPv6 address with a CIDR prefix, such as 2001:db8::10/64.
validate_ipv6_cidr() {
    python3 -c 'import ipaddress, sys; ipaddress.IPv6Interface(sys.argv[1])' "$1" >/dev/null 2>&1
}

# Convert a CIDR prefix length to the dotted-decimal netmask required by ifupdown.
cidr_to_netmask() {
    local prefix="$1" octet
    local -a octets=()
    local index

    for ((index = 0; index < 4; index++)); do
        if (( prefix >= 8 )); then
            octet=255
            prefix=$((prefix - 8))
        elif (( prefix > 0 )); then
            octet=$((256 - 2 ** (8 - prefix)))
            prefix=0
        else
            octet=0
        fi
        octets+=("$octet")
    done

    (IFS=.; printf '%s\n' "${octets[*]}")
}

# Append IPv4 and optional IPv6 stanzas for one interface to an ifupdown configuration file.
write_interface_stanza() {
    local iface="$1" ipv4_address_spec="$2" ipv6_address_spec="$3"
    local address prefix netmask

    [[ -n "$iface" && -n "$ipv4_address_spec" ]] || return 0
    
    printf 'allow-hotplug %s\n' "$iface"
    
    if uses_dhcp "$ipv4_address_spec"; then
        printf 'iface %s inet dhcp\n\n' "$iface"
    else
        validate_ipv4_cidr "$ipv4_address_spec" || fatal "Invalid IPv4 address/mask for ${iface}: ${ipv4_address_spec}."
        address="${ipv4_address_spec%/*}"
        prefix="${ipv4_address_spec#*/}"
        netmask="$(cidr_to_netmask "$prefix")"
        printf 'iface %s inet static\n    address %s\n    netmask %s\n\n' "$iface" "$address" "$netmask"
    fi

    [[ -n "$ipv6_address_spec" ]] || return 0
   
    if uses_dhcp "$ipv6_address_spec"; then
        printf 'iface %s inet6 dhcp\n\n' "$iface"
        return 0
    fi
   
    if uses_ipv6_auto "$ipv6_address_spec"; then
        printf 'iface %s inet6 auto\n\n' "$iface"
        return 0
    fi

    validate_ipv6_cidr "$ipv6_address_spec" || fatal "Invalid IPv6 address/prefix for ${iface}: ${ipv6_address_spec}."
   
    address="${ipv6_address_spec%/*}"
    prefix="${ipv6_address_spec#*/}"
   
    printf 'iface %s inet6 static\n    address %s\n    netmask %s\n\n' "$iface" "$address" "$prefix"
}

# Identify Linux distributions that use ifupdown and /etc/network/interfaces.
is_debian_family() {
    local distro_id distro_like

    [[ -r /etc/os-release ]] || fatal "/etc/os-release was not found."
   
    . /etc/os-release
   
    distro_id="${ID:-}"
    distro_like="${ID_LIKE:-}"
   
    [[ "$distro_id" == "debian" || "$distro_id" == "ubuntu" || " $distro_like " == *" debian "* ]]
}

# Install a boot-time activation unit for interfaces declared with allow-hotplug.
# networking.service only runs ifup -a, which does not include that interface class.
# Some systems rename network devices after networking.service starts, so wait for
# the requested interface names before invoking ifup.
install_hotplug_activation_service() {
    local tmp_file

    tmp_file="$(mktemp)"

    printf '%s\n' \
        '[Unit]' \
        'Description=Activate ArmFirewall allow-hotplug network interfaces' \
        'Wants=networking.service' \
        'After=networking.service' \
        '' \
        '[Service]' \
        'Type=oneshot' \
        'TimeoutStartSec=75' \
        "ExecStartPre=/bin/sh -ec 'for interface in ${LAN_IFACE} ${WAN_IFACE}; do attempts=0; until /sbin/ip link show dev \"\$\${interface}\" >/dev/null 2>&1; do attempts=\$\$((attempts + 1)); [ \"\$\${attempts}\" -lt 30 ] || exit 1; sleep 1; done; done'" \
        'ExecStart=/sbin/ifup --allow=hotplug -a' \
        'RemainAfterExit=yes' \
        '' \
        '[Install]' \
        'WantedBy=multi-user.target' > "$tmp_file"
    
    install -m 0644 "$tmp_file" "$ARMFIREWALL_HOTPLUG_UNIT_FILE"
    rm -f "$tmp_file"

    systemctl daemon-reload
    systemctl enable "$ARMFIREWALL_HOTPLUG_UNIT"
}

# Configure requested network interfaces through Debian's ifupdown backend.
configure_debian_interfaces() {
    local tmp_file iface applied_iface=""

    mkdir -p "$NETWORK_INTERFACES_DIR"
    
    if [[ ! -f "$NETWORK_INTERFACES_FILE" ]]; then
        printf 'auto lo\niface lo inet loopback\nsource %s/*\n' "$NETWORK_INTERFACES_DIR" > "$NETWORK_INTERFACES_FILE"
    elif ! grep -Fqx "source ${NETWORK_INTERFACES_DIR}/*" "$NETWORK_INTERFACES_FILE"; then
        printf '\nsource %s/*\n' "$NETWORK_INTERFACES_DIR" >> "$NETWORK_INTERFACES_FILE"
    fi

    tmp_file="$(mktemp "${NETWORK_INTERFACES_DIR}/.armfirewall.XXXXXX")"
    {
        printf '# Managed by ArmFirewall installer.\n'
        write_interface_stanza "$LAN_IFACE" "$LAN_IPV4_ADDR" "$LAN_IPV6_ADDR"
        write_interface_stanza "$WAN_IFACE" "$WAN_IPV4_ADDR" "$WAN_IPV6_ADDR"
    } > "$tmp_file"
    install -m 0644 "$tmp_file" "$ARMFIREWALL_INTERFACES_FILE"
    rm -f "$tmp_file"

    systemctl disable --now NetworkManager.service >/dev/null 2>&1 || true
    systemctl disable --now NetworkManager-wait-online.service >/dev/null 2>&1 || true
    systemctl enable networking.service
   
    install_hotplug_activation_service
   
    log "Restarting networking.service."
    systemctl restart networking.service

    for iface in "$LAN_IFACE" "$WAN_IFACE"; do
        [[ -n "$iface" && "$iface" != "$applied_iface" ]] || continue
       
        applied_iface="$iface"
       
        log "Applying network configuration on ${iface}."
        ifdown --force "$iface" >/dev/null 2>&1 || true
        ifup "$iface" || fatal "Could not apply network configuration on ${iface}."
    done
    
    log "Configured Debian interfaces in ${ARMFIREWALL_INTERFACES_FILE} and disabled NetworkManager."
}

main() {
    LAN_IFACE="${1:-}"
    LAN_IPV4_ADDR="${2:-}"
    WAN_IFACE="${3:-}"
    WAN_IPV4_ADDR="${4:-}"
    LAN_IPV6_ADDR="${5:-}"
    WAN_IPV6_ADDR="${6:-}"

    [[ -n "$LAN_IPV4_ADDR$WAN_IPV4_ADDR" ]] || return 0

    for address_spec in "$LAN_IPV4_ADDR" "$WAN_IPV4_ADDR"; do
        uses_dhcp "$address_spec" || validate_ipv4_cidr "$address_spec" || fatal "Invalid IPv4 address/mask: ${address_spec}."
    done
    
    for address_spec in "$LAN_IPV6_ADDR" "$WAN_IPV6_ADDR"; do
        [[ -z "$address_spec" ]] || uses_dhcp "$address_spec" || uses_ipv6_auto "$address_spec" || validate_ipv6_cidr "$address_spec" || fatal "Invalid IPv6 address/prefix: ${address_spec}."
    done
    
    is_debian_family || {
        log "Network reconfiguration is currently supported only on Debian-family systems; leaving the active network backend unchanged."
        return 0
    }
    
    configure_debian_interfaces
}

main "$@"
