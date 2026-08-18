#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

NETWORK_INTERFACES_FILE="/etc/network/interfaces"
NETWORK_INTERFACES_DIR="/etc/network/interfaces.d"
ARMFIREWALL_INTERFACES_FILE="${NETWORK_INTERFACES_DIR}/armfirewall"

# Return success when an address specification requests DHCP.
ipv4_uses_dhcp() {
    [[ "${1:-}" == "dhcp" ]]
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

# Append a stanza for one interface to an ifupdown configuration file.
write_interface_stanza() {
    local iface="$1" address_spec="$2"
    local address prefix netmask

    [[ -n "$iface" && -n "$address_spec" ]] || return 0
    printf 'allow-hotplug %s\n' "$iface"
    if ipv4_uses_dhcp "$address_spec"; then
        printf 'iface %s inet dhcp\n\n' "$iface"
        return 0
    fi

    validate_ipv4_cidr "$address_spec" || fatal "Invalid IPv4 address/mask for ${iface}: ${address_spec}."
    address="${address_spec%/*}"
    prefix="${address_spec#*/}"
    netmask="$(cidr_to_netmask "$prefix")"
    printf 'iface %s inet static\n    address %s\n    netmask %s\n\n' "$iface" "$address" "$netmask"
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

# Configure requested network interfaces through Debian's ifupdown backend.
configure_debian_interfaces() {
    local tmp_file

    mkdir -p "$NETWORK_INTERFACES_DIR"
    if [[ ! -f "$NETWORK_INTERFACES_FILE" ]]; then
        printf 'auto lo\niface lo inet loopback\nsource %s/*\n' "$NETWORK_INTERFACES_DIR" > "$NETWORK_INTERFACES_FILE"
    elif ! grep -Fqx "source ${NETWORK_INTERFACES_DIR}/*" "$NETWORK_INTERFACES_FILE"; then
        printf '\nsource %s/*\n' "$NETWORK_INTERFACES_DIR" >> "$NETWORK_INTERFACES_FILE"
    fi

    tmp_file="$(mktemp "${NETWORK_INTERFACES_DIR}/.armfirewall.XXXXXX")"
    {
        printf '# Managed by ArmFirewall installer.\n'
        write_interface_stanza "$LAN_IFACE" "$LAN_IPV4_ADDR"
        write_interface_stanza "$WAN_IFACE" "$WAN_IPV4_ADDR"
    } > "$tmp_file"
    install -m 0644 "$tmp_file" "$ARMFIREWALL_INTERFACES_FILE"
    rm -f "$tmp_file"

    systemctl disable --now NetworkManager.service >/dev/null 2>&1 || true
    systemctl disable --now NetworkManager-wait-online.service >/dev/null 2>&1 || true
    systemctl enable networking.service
    systemctl restart networking.service
    log "Configured Debian interfaces in ${ARMFIREWALL_INTERFACES_FILE} and disabled NetworkManager."
}

main() {
    LAN_IFACE="${1:-}"
    LAN_IPV4_ADDR="${2:-}"
    WAN_IFACE="${3:-}"
    WAN_IPV4_ADDR="${4:-}"

    [[ -n "$LAN_IPV4_ADDR$WAN_IPV4_ADDR" ]] || return 0
    for address_spec in "$LAN_IPV4_ADDR" "$WAN_IPV4_ADDR"; do
        [[ -z "$address_spec" ]] || ipv4_uses_dhcp "$address_spec" || validate_ipv4_cidr "$address_spec" || fatal "Invalid IPv4 address/mask: ${address_spec}."
    done
    is_debian_family || {
        log "Network reconfiguration is currently supported only on Debian-family systems; leaving the active network backend unchanged."
        return 0
    }
    configure_debian_interfaces
}

main "$@"
