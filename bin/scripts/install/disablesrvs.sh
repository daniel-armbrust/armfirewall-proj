#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# shellcheck source=../common/log.sh
declare -F fatal >/dev/null 2>&1 || . "$ROOT_DIR/bin/scripts/common/log.sh"

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

# Return success when systemd knows about one unit.
systemd_unit_known() {
    local unit="$1"
    local load_state

    command -v systemctl >/dev/null 2>&1 || return 1
    load_state="$(systemctl show --property=LoadState --value "$unit" 2>/dev/null || true)"
    [[ -n "$load_state" && "$load_state" != "not-found" ]]
}

# Return success only when a systemd unit is actively enabled for startup.
systemd_unit_enabled() {
    case "$(systemctl is-enabled "$1" 2>/dev/null || true)" in
        enabled|enabled-runtime|linked|linked-runtime)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Stop and disable one systemd unit when it exists.
stop_disable_systemd_unit() {
    local unit="$1"

    systemd_unit_known "$unit" || {
        log "OS service is not installed: ${unit}."
        return 0
    }

    if systemctl is-active --quiet "$unit"; then
        log "Stopping OS service: ${unit}."
        systemctl stop "$unit" || fatal "Could not stop OS service: ${unit}."
    fi

    if systemctl is-active --quiet "$unit"; then
        fatal "OS service is still active after stop attempt: ${unit}."
    fi

    if systemd_unit_enabled "$unit"; then
        log "Disabling OS service: ${unit}."
        systemctl disable "$unit" >/dev/null 2>&1 || \
            fatal "Could not disable OS service: ${unit}."
    fi

    if systemd_unit_enabled "$unit"; then
        fatal "OS service is still enabled after disable attempt: ${unit}."
    fi
}

# Stop and disable one systemd service when it exists.
stop_disable_systemd_service() {
    stop_disable_systemd_unit "${1%.service}.service"
}

# Stop and disable one systemd socket when it exists.
stop_disable_systemd_socket() {
    stop_disable_systemd_unit "${1%.socket}.socket"
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

# Disable optional desktop, discovery, modem, Bluetooth, and Wi-Fi services.
disable_unneeded_services() {
    local service

    for service in gdm gdm3 display-manager cups cups-browsed avahi-daemon ModemManager bluetooth wpa_supplicant; do
        stop_disable_systemd_service "$service"
    done
    stop_disable_systemd_socket avahi-daemon
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
    disable_unneeded_services
}

main "$@"
