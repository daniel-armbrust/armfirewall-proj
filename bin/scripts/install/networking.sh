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
    [[ "${1:-}" == "dhcp" || "${1:-}" == "auto" ]]
}

# Return success when an IPv6 address specification requests SLAAC.
uses_ipv6_auto() {
    [[ "${1:-}" == "auto" ]]
}

# Return success when IPv6 prefix delegation is requested for router mode.
ipv6_prefix_delegation_requested() {
    [[ "${ROUTER_MODE:-0}" == "1" ]] || return 1
    uses_dhcp "${WAN_IPV6_ADDR:-}" && uses_dhcp "${LAN_IPV6_ADDR:-}"
}

# With no NetworkManager, dhcpcd owns DHCPv6/RA processing for dynamic PD.
# Do not generate ifupdown IPv6 stanzas for its WAN and delegated LAN.
legacy_ipv6_pd_requested() {
    ipv6_prefix_delegation_requested
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
    local iface="$1" ipv4_address_spec="$2" ipv6_address_spec="$3" ipv4_gateway="$4" ipv6_gateway="$5" allow_default="$6"
    local address prefix netmask

    [[ -n "$iface" && -n "$ipv4_address_spec" ]] || return 0
    
    printf 'allow-hotplug %s\n' "$iface"
    
    if uses_dhcp "$ipv4_address_spec"; then
        printf 'iface %s inet dhcp\n' "$iface"
        [[ "$allow_default" == "yes" ]] || printf '    post-up /sbin/ip route del default dev %s || true\n' "$iface"
        printf '\n'
    else
        validate_ipv4_cidr "$ipv4_address_spec" || fatal "Invalid IPv4 address/mask for ${iface}: ${ipv4_address_spec}."
        address="${ipv4_address_spec%/*}"
        prefix="${ipv4_address_spec#*/}"
        netmask="$(cidr_to_netmask "$prefix")"
        printf 'iface %s inet static\n    address %s\n    netmask %s\n' "$iface" "$address" "$netmask"
        [[ "$allow_default" != "yes" || -z "$ipv4_gateway" ]] || printf '    gateway %s\n' "$ipv4_gateway"
        printf '\n'
    fi

    [[ -n "$ipv6_address_spec" ]] || return 0
    if legacy_ipv6_pd_requested && [[ "$iface" == "${WAN_IFACE:-}" || "$iface" == "${LAN_IFACE:-}" ]]; then
        printf '# IPv6 on %s is managed by the ArmFirewall prefix-delegation client.\n\n' "$iface"
        return 0
    fi
   
    if uses_dhcp "$ipv6_address_spec"; then
        printf 'iface %s inet6 dhcp\n' "$iface"
        [[ "$allow_default" == "yes" ]] || printf '    post-up /sbin/ip -6 route del default dev %s || true\n' "$iface"
        printf '\n'
        return 0
    fi
   
    if uses_ipv6_auto "$ipv6_address_spec"; then
        printf 'iface %s inet6 auto\n' "$iface"
        [[ "$allow_default" == "yes" ]] || printf '    post-up /sbin/ip -6 route del default dev %s || true\n' "$iface"
        printf '\n'
        return 0
    fi

    validate_ipv6_cidr "$ipv6_address_spec" || fatal "Invalid IPv6 address/prefix for ${iface}: ${ipv6_address_spec}."
   
    address="${ipv6_address_spec%/*}"
    prefix="${ipv6_address_spec#*/}"
   
    printf 'iface %s inet6 static\n    address %s\n    netmask %s\n' "$iface" "$address" "$prefix"
    [[ -z "$ipv6_gateway" ]] || printf '    gateway %s\n' "$ipv6_gateway"
    printf '\n'
}

# Return success when NetworkManager can be configured through nmcli.
networkmanager_available() {
    command -v nmcli >/dev/null 2>&1
}

# Remove only network files and units created by the legacy ArmFirewall ifupdown backend.
cleanup_legacy_ifupdown_backend() {
    rm -f "$ARMFIREWALL_INTERFACES_FILE"

    command -v systemctl >/dev/null 2>&1 || return 0
    systemctl disable --now "$ARMFIREWALL_HOTPLUG_UNIT" >/dev/null 2>&1 || true
    rm -f "$ARMFIREWALL_HOTPLUG_UNIT_FILE"
    
    systemctl daemon-reload
    systemctl disable networking.service >/dev/null 2>&1 || true
}

# Return the UUID of the active NetworkManager connection for an interface.
networkmanager_active_connection_uuid() {
    local iface="$1" uuid

    uuid="$(nmcli -g GENERAL.CON-UUID device show "$iface" 2>/dev/null | head -n 1 || true)"
    [[ -n "$uuid" && "$uuid" != "--" ]] && printf '%s\n' "$uuid"
}

# Return one persisted NetworkManager connection UUID bound to an interface.
networkmanager_profile_uuid_for_interface() {
    local iface="$1" uuid profile_iface

    while IFS= read -r uuid; do
        [[ -n "$uuid" ]] || continue
        profile_iface="$(nmcli -g connection.interface-name connection show uuid "$uuid" 2>/dev/null | head -n 1 || true)"
        [[ "$profile_iface" == "$iface" ]] && {
            printf '%s\n' "$uuid"
            return 0
        }
    done < <(nmcli -g UUID connection show 2>/dev/null || true)

    return 1
}

# Return a connection UUID for an interface, creating an unambiguous profile when needed.
networkmanager_connection_for_interface() {
    local iface="$1" connection_uuid

    connection_uuid="$(networkmanager_active_connection_uuid "$iface" || true)"
    [[ -n "$connection_uuid" ]] || connection_uuid="$(networkmanager_profile_uuid_for_interface "$iface" || true)"
    
    if [[ -z "$connection_uuid" ]]; then
        connection_uuid="$(cat /proc/sys/kernel/random/uuid)"
        nmcli connection add type ethernet ifname "$iface" con-name "armfirewall-${iface}" \
            connection.uuid "$connection_uuid" autoconnect yes >/dev/null || \
            fatal "Could not create the NetworkManager connection for ${iface}."
    fi
   
    printf '%s\n' "$connection_uuid"
}

# Apply an IPv4 DHCP or static configuration to one NetworkManager connection.
configure_networkmanager_ipv4() {
    local connection="$1" address_spec="$2" gateway="$3"

    if uses_dhcp "$address_spec"; then
        nmcli connection modify "$connection" \
            ipv4.method auto ipv4.addresses "" ipv4.gateway "" || \
            fatal "Could not configure IPv4 DHCP for NetworkManager connection ${connection}."
        return 0
    fi

    nmcli connection modify "$connection" \
        ipv4.method manual ipv4.addresses "$address_spec" ipv4.gateway "$gateway" || \
        fatal "Could not configure static IPv4 for NetworkManager connection ${connection}."
}

# Apply optional IPv6 configuration to one NetworkManager connection.
configure_networkmanager_ipv6() {
    local connection="$1" address_spec="$2" gateway="$3"

    [[ -n "$address_spec" ]] || return 0
    if uses_dhcp "$address_spec" || uses_ipv6_auto "$address_spec"; then
        # NetworkManager's automatic method processes Router Advertisements and DHCPv6.
        nmcli connection modify "$connection" \
            ipv6.method auto ipv6.addresses "" ipv6.gateway "" || \
            fatal "Could not configure automatic IPv6 for NetworkManager connection ${connection}."
        return 0
    fi

    nmcli connection modify "$connection" \
        ipv6.method manual ipv6.addresses "$address_spec" ipv6.gateway "$gateway" || \
        fatal "Could not configure static IPv6 for NetworkManager connection ${connection}."
}

# Permit a default route and automatic DNS only on the selected WAN connection.
configure_networkmanager_default_route_policy() {
    local connection="$1" allow_default="$2"
    local never_default="yes" ignore_auto_dns="yes"

    if [[ "$allow_default" == "yes" ]]; then
        never_default="no"
        ignore_auto_dns="no"
    fi

    nmcli connection modify "$connection" \
        ipv4.never-default "$never_default" ipv4.ignore-auto-dns "$ignore_auto_dns" \
        ipv6.never-default "$never_default" ipv6.ignore-auto-dns "$ignore_auto_dns" || \
        fatal "Could not configure the default-route policy for NetworkManager connection ${connection}."
}

# Return NetworkManager Ethernet devices, excluding loopback and virtual devices.
networkmanager_ethernet_interfaces() {
    local iface device_type

    while IFS=: read -r iface device_type; do
        [[ -n "$iface" && "$iface" != "lo" && "$device_type" == "ethernet" ]] || continue
        printf '%s\n' "$iface"
    done < <(nmcli -t -f DEVICE,TYPE device status)
}

# Return success when an Ethernet interface has a physical link.
network_interface_has_carrier() {
    local iface="$1"

    [[ -r "/sys/class/net/${iface}/carrier" ]] || return 1
    [[ "$(<"/sys/class/net/${iface}/carrier")" == "1" ]]
}

# Configure requested interfaces through the operating system's NetworkManager backend.
configure_networkmanager_interfaces() {
    local iface ipv4_address_spec ipv4_gateway ipv6_address_spec ipv6_gateway connection applied_iface="" allow_default
    local -a ifaces=("$LAN_IFACE" "$WAN_IFACE")
    local -a ipv4_addresses=("$LAN_IPV4_ADDR" "$WAN_IPV4_ADDR")
    local -a ipv4_gateways=("$LAN_IPV4_GATEWAY" "$WAN_IPV4_GATEWAY")
    local -a ipv6_addresses=("$LAN_IPV6_ADDR" "$WAN_IPV6_ADDR")
    local -a ipv6_gateways=("$LAN_IPV6_GATEWAY" "$WAN_IPV6_GATEWAY")
    local index

    cleanup_legacy_ifupdown_backend

    if command -v systemctl >/dev/null 2>&1; then
        systemctl enable --now NetworkManager.service || fatal "Could not enable NetworkManager."
    fi

    for index in "${!ifaces[@]}"; do
        iface="${ifaces[$index]}"
        ipv4_address_spec="${ipv4_addresses[$index]}"
        ipv4_gateway="${ipv4_gateways[$index]}"
        ipv6_address_spec="${ipv6_addresses[$index]}"
        ipv6_gateway="${ipv6_gateways[$index]}"
        [[ -n "$iface" && "$iface" != "$applied_iface" ]] || continue
        applied_iface="$iface"

        ip link show dev "$iface" >/dev/null 2>&1 || fatal "Network interface was not found: ${iface}."
        nmcli device set "$iface" managed yes || fatal "Could not mark ${iface} as managed by NetworkManager."
        
        connection="$(networkmanager_connection_for_interface "$iface")"
        
        nmcli connection modify "$connection" connection.interface-name "$iface" connection.autoconnect yes || \
            fatal "Could not prepare the NetworkManager connection for ${iface}."
        
        allow_default="no"
        [[ "$iface" == "$WAN_IFACE" ]] && allow_default="yes"
        [[ "$allow_default" == "yes" ]] || ipv4_gateway=""

        configure_networkmanager_ipv4 "$connection" "$ipv4_address_spec" "$ipv4_gateway"
        configure_networkmanager_ipv6 "$connection" "$ipv6_address_spec" "$ipv6_gateway"
        configure_networkmanager_default_route_policy "$connection" "$allow_default"

        if network_interface_has_carrier "$iface"; then
            log "Applying NetworkManager configuration on ${iface}."
            nmcli connection up "$connection" ifname "$iface" >/dev/null || \
                fatal "Could not activate the NetworkManager connection on ${iface}."
        else
            log "Saved NetworkManager configuration for ${iface}; activation will occur when a physical link is detected."
        fi
    done

    # Keep every additional Ethernet interface on IPv4 DHCP, without letting
    # an incidental gateway replace the WAN's default route or DNS. When WAN
    # prefix delegation is active, only the explicit WAN may receive IPv6.
    while IFS= read -r iface; do
        [[ "$iface" != "$WAN_IFACE" && "$iface" != "$LAN_IFACE" ]] || continue

        connection="$(networkmanager_connection_for_interface "$iface")"
        nmcli connection modify "$connection" connection.interface-name "$iface" connection.autoconnect yes || \
            fatal "Could not prepare the NetworkManager connection for ${iface}."
        configure_networkmanager_ipv4 "$connection" "dhcp" ""
        configure_networkmanager_default_route_policy "$connection" no

        if ipv6_prefix_delegation_requested; then
            nmcli connection modify "$connection" \
                ipv6.method ignore ipv6.addresses "" ipv6.gateway "" ipv6.dns "" \
                ipv6.never-default yes ipv6.ignore-auto-routes yes ipv6.ignore-auto-dns yes || \
                fatal "Could not reserve IPv6 prefix delegation for the WAN on ${iface}."
        fi

        if network_interface_has_carrier "$iface"; then
            nmcli connection up "$connection" ifname "$iface" >/dev/null || \
                fatal "Could not activate the NetworkManager connection on ${iface}."
        fi
    done < <(networkmanager_ethernet_interfaces)

    log "Configured network interfaces through NetworkManager."
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
        write_interface_stanza "$LAN_IFACE" "$LAN_IPV4_ADDR" "$LAN_IPV6_ADDR" "$LAN_IPV4_GATEWAY" "$LAN_IPV6_GATEWAY" no
        write_interface_stanza "$WAN_IFACE" "$WAN_IPV4_ADDR" "$WAN_IPV6_ADDR" "$WAN_IPV4_GATEWAY" "$WAN_IPV6_GATEWAY" yes
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
    LAN_IPV4_GATEWAY="${7:-}"
    WAN_IPV4_GATEWAY="${8:-}"
    LAN_IPV6_GATEWAY="${9:-}"
    WAN_IPV6_GATEWAY="${10:-}"

    [[ -n "$LAN_IPV4_ADDR$WAN_IPV4_ADDR" ]] || return 0

    for address_spec in "$LAN_IPV4_ADDR" "$WAN_IPV4_ADDR"; do
        uses_dhcp "$address_spec" || validate_ipv4_cidr "$address_spec" || fatal "Invalid IPv4 address/mask: ${address_spec}."
    done
    for gateway in "$LAN_IPV4_GATEWAY" "$WAN_IPV4_GATEWAY"; do
        [[ -z "$gateway" ]] || validate_ipv4_cidr "${gateway}/32" || fatal "Invalid IPv4 gateway: ${gateway}."
    done
    for gateway in "$LAN_IPV6_GATEWAY" "$WAN_IPV6_GATEWAY"; do
        [[ -z "$gateway" ]] || python3 -c 'import ipaddress, sys; ipaddress.IPv6Address(sys.argv[1])' "$gateway" >/dev/null 2>&1 || fatal "Invalid IPv6 gateway: ${gateway}."
    done
    
    for address_spec in "$LAN_IPV6_ADDR" "$WAN_IPV6_ADDR"; do
        [[ -z "$address_spec" ]] || uses_dhcp "$address_spec" || uses_ipv6_auto "$address_spec" || validate_ipv6_cidr "$address_spec" || fatal "Invalid IPv6 address/prefix: ${address_spec}."
    done
    
    if networkmanager_available; then
        configure_networkmanager_interfaces
        return 0
    fi

    is_debian_family || {
        log "NetworkManager is unavailable and network reconfiguration is currently supported only on Debian-family systems; leaving the active network backend unchanged."
        return 0
    }

    log "NetworkManager is unavailable; using the Debian ifupdown fallback."
    configure_debian_interfaces
}

main "$@"
