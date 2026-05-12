#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export LAN_IFACE=""

# shellcheck source=scripts/globals.sh
. "$ROOT_DIR/bin/scripts/globals.sh"

# Print command install.sh usage
usage() {
    cat <<USAGE
Usage: $0 --lan-iface <iface>

Options:
  --lan-iface <iface>  LAN network interface to persist in iface.db
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
}

main() {
    # Parse install command line arguments
    parse_args "$@"

    # Ensure the script is running with root privileges
    need_root

    # Configures the operating system package repositories used by ArmFirewall
    "$ROOT_DIR/bin/scripts/addpkgmirrors.sh"

    # Installs operating system dependencies and prepares the Python runtime
    "$ROOT_DIR/bin/scripts/osdeps.sh"

    # Creates SQLite DB files from DDLs files
    "$ROOT_DIR/bin/scripts/createdb.sh"

    # Validate and persist the selected LAN interface in iface.db
    "$ROOT_DIR/bin/scripts/laniface.sh"

    # TODO: apply firewall rules
    "$ROOT_DIR/bin/scripts/fwrules.sh"

    # Ensures the default protected admin account exists in the users database
    "$ROOT_DIR/bin/scripts/adminusr.sh"

    # Generates and secures the self-signed TLS certificate used by the 
    # ArmFirewall web API
    "$ROOT_DIR/bin/scripts/sslcert.sh"

    # Creates the operating system user used by supervisord-managed services
    "$ROOT_DIR/bin/scripts/osuser.sh"

    # Creates supervisord and systemd service manager files
    "$ROOT_DIR/bin/scripts/supervisord.sh"
}

main "$@"
