#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=scripts/common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Flush all managed iptables/ip6tables tables before rebuilding runtime state.
flush_firewall_rules() {
    local cmd table

    log "Flushing IPv4 and IPv6 filter, mangle and nat rules."
    for cmd in iptables ip6tables; do
        has_cmd "$cmd" || {
            log "Skipping missing firewall command: ${cmd}."
            continue
        }
        for table in filter mangle nat; do
            "$cmd" -t "$table" -F || true
            "$cmd" -t "$table" -X || true
        done
    done
}

# Apply persisted runtime state before supervisord starts ArmFirewall services.
main() {
    # Print pre-start banner
    print_banner "pre-start"

    # Ensure the script is running with root privileges
    need_root

    # Clear managed firewall tables before rebuilding persisted runtime state.
    flush_firewall_rules

    # Reapply persisted filter firewall rules.
    "$ROOT_DIR/bin/scripts/startpre/filterules.sh" || fatal "Could not apply persisted filter firewall rules."

    # Reapply persisted NAT firewall rules.
    "$ROOT_DIR/bin/scripts/startpre/natrules.sh" || fatal "Could not apply persisted NAT firewall rules."

    # Reapply persisted mangle firewall rules.
    "$ROOT_DIR/bin/scripts/startpre/manglerules.sh" || fatal "Could not apply persisted mangle firewall rules."

    # Reapply persisted kernel parameters stored in proc.db.
    "$ROOT_DIR/bin/scripts/startpre/proc.sh" || fatal "Could not apply persisted kernel proc settings."

    # Reapply persisted policy routing tables, routes, and rules.
    "$ROOT_DIR/bin/scripts/startpre/routetable.sh" || fatal "Could not apply persisted policy routing state."

    log "ArmFirewall pre-start completed successfully."
}

main "$@"
