#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SET_HOSTNAME=""
TIMEZONE=""
LAN_IPV4_ADDR=""
WAN_IPV4_ADDR=""
LAN_IPV6_ADDR=""
WAN_IPV6_ADDR=""
LAN_IPV4_GATEWAY=""
WAN_IPV4_GATEWAY=""

# shellcheck source=scripts/common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Print command install.sh usage
usage() {
    cat <<USAGE
Usage: $0 --lan-iface <iface> --lan-ipv4-addr <IPv4/CIDR|dhcp|auto>
          --wan-iface <iface> --wan-ipv4-addr <IPv4/CIDR|dhcp|auto>
          [--lan-ipv4-gateway <IPv4>] [--wan-ipv4-gateway <IPv4>]
          [--lan-ipv6-addr <IPv6/CIDR|dhcp|auto>]
          [--wan-ipv6-addr <IPv6/CIDR|dhcp|auto>]
          [--router-mode] [--set-hostname <name>] [--timezone <Region/City>]

Options:
  --lan-iface <iface>          LAN network interface to persist in iface.db
  --lan-ipv4-addr <addr>       Set LAN IPv4 address/mask, dhcp, or auto.
  --lan-ipv4-gateway <addr>    Optional LAN IPv4 gateway for a static address.
  --lan-ipv6-addr <addr>       Optional LAN IPv6 address/prefix, dhcp, or auto.
  
  --wan-iface <iface>          WAN network interface to persist in iface.db
  --wan-ipv4-addr <addr>       Set WAN IPv4 address/mask, dhcp, or auto.
  --wan-ipv4-gateway <addr>    Optional WAN IPv4 gateway for a static address.
  --wan-ipv6-addr <addr>       Optional WAN IPv6 address/prefix, dhcp, or auto.
  
  --router-mode                Enable routing, forwarding, and NAT. Requires --wan-iface
  
  --set-hostname <name>        Set the system hostname (a hostname or FQDN).
  
  --timezone <Region/City>     Set the system timezone, e.g. America/Sao_Paulo.
  
  -h, --help                   Show this help message

USAGE
}

# Parse install command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --lan-iface)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--lan-iface requires an interface name"
                LAN_IFACE="$2"
                shift 2
                ;;

            --wan-iface)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--wan-iface requires an interface name"
                WAN_IFACE="$2"
                shift 2
                ;;

            --router-mode)
                ROUTER_MODE=1
                shift
                ;;

            --set-hostname)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--set-hostname requires a hostname."
                SET_HOSTNAME="$2"
                shift 2
                ;;

            --timezone)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--timezone requires a timezone, e.g. America/Sao_Paulo."
                TIMEZONE="$2"
                shift 2
                ;;

            --lan-ipv4-addr)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--lan-ipv4-addr requires an IPv4 address/mask, dhcp, or auto."
                LAN_IPV4_ADDR="$2"
                shift 2
                ;;

            --wan-ipv4-addr)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--wan-ipv4-addr requires an IPv4 address/mask, dhcp, or auto."
                WAN_IPV4_ADDR="$2"
                shift 2
                ;;

            --lan-ipv6-addr)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--lan-ipv6-addr requires an IPv6 address/prefix, dhcp, or auto."
                LAN_IPV6_ADDR="$2"
                shift 2
                ;;

            --wan-ipv6-addr)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--wan-ipv6-addr requires an IPv6 address/prefix, dhcp, or auto."
                WAN_IPV6_ADDR="$2"
                shift 2
                ;;

            --lan-ipv4-gateway)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--lan-ipv4-gateway requires an IPv4 address."
                LAN_IPV4_GATEWAY="$2"
                shift 2
                ;;

            --wan-ipv4-gateway)
                [[ $# -ge 2 && -n "${2:-}" ]] || fatal "--wan-ipv4-gateway requires an IPv4 address."
                WAN_IPV4_GATEWAY="$2"
                shift 2
                ;;

            -h|--help)
                usage
                exit 0
                ;;

            *)
                fatal "Unknown install option: $1"
                ;;
        esac
    done

    [[ -n "$LAN_IFACE" ]] || fatal "Missing required option: --lan-iface <iface>."
    [[ -n "$LAN_IPV4_ADDR" ]] || fatal "Missing required option: --lan-ipv4-addr <IPv4/CIDR|dhcp|auto>."
    [[ -n "$WAN_IFACE" ]] || fatal "Missing required option: --wan-iface <iface>."
    [[ -n "$WAN_IPV4_ADDR" ]] || fatal "Missing required option: --wan-ipv4-addr <IPv4/CIDR|dhcp|auto>."
}

main() {
    # Print installer banner
    print_banner "installer"

    # Parse install command line arguments
    parse_args "$@"

    # Ensure the script is running with root privileges
    need_root

    "$ROOT_DIR/bin/scripts/install/hostname.sh" "$SET_HOSTNAME" "$LAN_IPV4_ADDR"
    "$ROOT_DIR/bin/scripts/install/timesync.sh" "$TIMEZONE"

    # Configures the operating system package repositories used by ArmFirewall
    "$ROOT_DIR/bin/scripts/install/addpkgmirrors.sh"

    # Installs operating system dependencies and prepares the Python runtime
    "$ROOT_DIR/bin/scripts/install/osdeps.sh"

    # Disables native OS firewall services before ArmFirewall owns rules
    "$ROOT_DIR/bin/scripts/install/disablesrvs.sh"

    # Creates SQLite DB files from DDLs files
    "$ROOT_DIR/bin/scripts/install/execddl.sh"

    # Validate and persist the selected LAN interface in iface.db
    "$ROOT_DIR/bin/scripts/install/laniface.sh"

    # TODO: apply firewall rules
    "$ROOT_DIR/bin/scripts/install/fwrules.sh"

    # Persist WAN and optionally enable router mode.
    "$ROOT_DIR/bin/scripts/install/routermode.sh"

    # Import current Linux route tables into policy-routing.db
    "$ROOT_DIR/bin/scripts/install/routetable.sh"

    # Ensures the default protected admin account exists in the users database
    "$ROOT_DIR/bin/scripts/install/adminusr.sh"

    # Generates and secures the self-signed TLS certificate used by the 
    # ArmFirewall web API
    "$ROOT_DIR/bin/scripts/install/sslcert.sh"

    # Creates the operating system user used by supervisord-managed services
    "$ROOT_DIR/bin/scripts/install/osuser.sh"

    # Creates supervisord and systemd service manager files
    "$ROOT_DIR/bin/scripts/install/supervisord.sh"

    "$ROOT_DIR/bin/scripts/install/networking.sh" \
        "$LAN_IFACE" "$LAN_IPV4_ADDR" "$WAN_IFACE" "$WAN_IPV4_ADDR" "$LAN_IPV6_ADDR" "$WAN_IPV6_ADDR" \
        "$LAN_IPV4_GATEWAY" "$WAN_IPV4_GATEWAY"

    # Request an IPv6 delegated prefix on WAN and allocate one /64 to LAN.
    "$ROOT_DIR/bin/scripts/install/ipv6pd.sh"
}

main "$@"
