#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Validate and persist an optional system hostname passed by install.sh.
set_system_hostname() {
    local requested_hostname="${1:-}"

    [[ -n "$requested_hostname" ]] || return 0
    [[ ${#requested_hostname} -le 253 ]] || fatal "--set-hostname must be at most 253 characters."
    [[ "$requested_hostname" =~ ^[[:alnum:]]([[:alnum:].-]*[[:alnum:]])?$ ]] || fatal "--set-hostname must be a valid hostname or FQDN."
    [[ "$requested_hostname" != *..* ]] || fatal "--set-hostname must not contain empty labels."

    has_cmd hostnamectl || fatal "hostnamectl is required to set the hostname."
    hostnamectl set-hostname "$requested_hostname"
    log "Set system hostname to ${requested_hostname}."
}

main() {
    set_system_hostname "${1:-}"
}

main "$@"
