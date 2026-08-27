#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Update hostname mappings in /etc/hosts for loopback and a static LAN IPv4 address.
update_hosts_file() {
    local requested_hostname="$1"
    local lan_ipv4_addr="$2"
    local lan_ipv4 tmp_file

    [[ "$lan_ipv4_addr" != "dhcp" && "$lan_ipv4_addr" != "auto" ]] || {
        log "LAN IPv4 uses automatic addressing; no static LAN hostname mapping was added to /etc/hosts."
        return 0
    }

    lan_ipv4="${lan_ipv4_addr%/*}"
    tmp_file="$(mktemp)"
    awk -v hostname="$requested_hostname" -v lan_ipv4="$lan_ipv4" '
        # Do not use the Debian 127.0.1.1 hostname convention.
        $1 == "127.0.1.1" { next }
        $1 == "127.0.0.1" {
            printf "127.0.0.1"
            for (field = 2; field <= NF; field++) {
                if ($field != hostname) printf "\t%s", $field
            }
            printf "\t%s\n", hostname
            loopback_found = 1
            next
        }
        $1 == lan_ipv4 {
            print lan_ipv4 "\t" hostname
            lan_found = 1
            next
        }
        { print }
        END {
            if (!loopback_found) print "127.0.0.1\tlocalhost\t" hostname
            if (!lan_found) print lan_ipv4 "\t" hostname
        }
    ' /etc/hosts > "$tmp_file"
    install -m 0644 "$tmp_file" /etc/hosts
    rm -f "$tmp_file"
    log "Updated /etc/hosts for hostname ${requested_hostname} and LAN IPv4 ${lan_ipv4}."
}

# Validate and persist an optional system hostname passed by install.sh.
set_system_hostname() {
    local requested_hostname="${1:-}"
    local lan_ipv4_addr="${2:-}"

    [[ -n "$requested_hostname" ]] || return 0
    [[ ${#requested_hostname} -le 253 ]] || fatal "--set-hostname must be at most 253 characters."
    [[ "$requested_hostname" =~ ^[[:alnum:]]([[:alnum:].-]*[[:alnum:]])?$ ]] || fatal "--set-hostname must be a valid hostname or FQDN."
    [[ "$requested_hostname" != *..* ]] || fatal "--set-hostname must not contain empty labels."

    has_cmd hostnamectl || fatal "hostnamectl is required to set the hostname."
    hostnamectl set-hostname "$requested_hostname"
    [[ -n "$lan_ipv4_addr" ]] && update_hosts_file "$requested_hostname" "$lan_ipv4_addr"
    log "Set system hostname to ${requested_hostname}."
}

main() {
    set_system_hostname "${1:-}" "${2:-}"
}

main "$@"
