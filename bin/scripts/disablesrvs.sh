#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=globals.sh
. "$ROOT_DIR/bin/scripts/globals.sh"

# shellcheck source=log.sh
declare -F fatal >/dev/null 2>&1 || . "$ROOT_DIR/bin/scripts/log.sh"

OS_ID=""
OS_ID_LIKE=""

# Load Linux distribution metadata used to select services.
load_os_info() {
    [[ -r /etc/os-release ]] || fatal "/etc/os-release was not found."

    . /etc/os-release

    OS_ID="${ID:-unknown}"
    OS_ID_LIKE="${ID_LIKE:-}"
}

# Return success when the current system is Oracle or Red Hat-like.
is_redhat_like() {
    [[ "$OS_ID" =~ ^(ol|oracle|oraclelinux|rhel|rocky|almalinux|centos|fedora)$ ]] || \
        [[ " ${OS_ID_LIKE} " == *" rhel "* ]] || \
        [[ " ${OS_ID_LIKE} " == *" fedora "* ]]
}

# Return success when the current system is Debian-like.
is_debian_like() {
    [[ "$OS_ID" =~ ^(debian|ubuntu)$ ]] || [[ " ${OS_ID_LIKE} " == *" debian "* ]]
}

# Return success when systemd knows about one service.
systemd_service_known() {
    local service="$1"

    command -v systemctl >/dev/null 2>&1 || return 1
    systemctl list-unit-files "${service}.service" >/dev/null 2>&1 && return 0
    systemctl status "${service}.service" >/dev/null 2>&1 && return 0

    return 1
}

# Stop and disable one systemd service when it exists.
stop_disable_systemd_service() {
    local service="$1"

    systemd_service_known "$service" || {
        log "OS firewall service is not installed: ${service}."
        return 0
    }

    if systemctl is-active --quiet "$service"; then
        log "Stopping OS firewall service: ${service}."
        systemctl stop "$service" || fatal "Could not stop OS firewall service: ${service}."
    fi

    if systemctl is-active --quiet "$service"; then
        fatal "OS firewall service is still active after stop attempt: ${service}."
    fi

    if systemctl is-enabled --quiet "$service" 2>/dev/null; then
        log "Disabling OS firewall service: ${service}."
        systemctl disable "$service" >/dev/null 2>&1 || \
            fatal "Could not disable OS firewall service: ${service}."
    fi

    if systemctl is-enabled --quiet "$service" 2>/dev/null; then
        fatal "OS firewall service is still enabled after disable attempt: ${service}."
    fi

    return 0
}

# Disable firewalld on Oracle Linux and Red Hat-like systems.
disable_firewalld() {
    stop_disable_systemd_service firewalld
}

# Disable ufw on Debian and Ubuntu systems.
disable_ufw() {
    if command -v ufw >/dev/null 2>&1; then
        log "Disabling ufw firewall policy."
        ufw --force disable >/dev/null 2>&1 || fatal "Could not disable ufw policy."
    fi

    stop_disable_systemd_service ufw
}

# Disable the native operating system firewall service for this distribution.
disable_os_firewall_services() {
    load_os_info

    if is_redhat_like; then
        log "Detected Red Hat-like system; disabling firewalld if present."
        disable_firewalld
        return 0
    fi

    if is_debian_like; then
        log "Detected Debian-like system; disabling ufw if present."
        disable_ufw
        return 0
    fi

    log "Unknown Linux family; checking firewalld and ufw."
    disable_firewalld
    disable_ufw
}

# Disable operating system firewall services before ArmFirewall rules are applied.
main() {
    need_root
    disable_os_firewall_services
}

main "$@"
