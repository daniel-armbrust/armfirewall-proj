#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=scripts/common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Print command install.sh usage
usage() {
    cat <<USAGE
Usage: $0 --lan-iface <iface> [--wan-iface <iface>] [--router-mode]

Options:
  --lan-iface <iface>  LAN network interface to persist in iface.db
  --wan-iface <iface>  WAN network interface to persist in iface.db
  --router-mode        Enable routing, forwarding, and NAT. Requires --wan-iface
  -h, --help           Show this help message
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
    [[ "$ROUTER_MODE" -eq 0 || -n "$WAN_IFACE" ]] || fatal "--router-mode requires --wan-iface <iface>."
}

main() {
    # Print installer banner
    print_banner "installer"

    # Parse install command line arguments
    parse_args "$@"

    # Ensure the script is running with root privileges
    need_root

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
}

main "$@"
