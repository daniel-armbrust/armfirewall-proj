#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

TIME_SYNC_SERVICE=""

# Start the first available systemd time synchronization service.
enable_systemd_time_service() {
    local service

    for service in chronyd.service chrony.service systemd-timesyncd.service ntp.service ntpd.service; do
        if systemctl enable --now "$service" >/dev/null 2>&1; then
            TIME_SYNC_SERVICE="$service"
            log "Enabled time synchronization service: ${service}."
            return 0
        fi
    done
    return 1
}

# Start the first available SysV-style time synchronization service.
enable_legacy_time_service() {
    local service

    has_cmd service || return 1
    for service in chronyd chrony ntpd ntp; do
        if service "$service" start >/dev/null 2>&1; then
            TIME_SYNC_SERVICE="$service"
            log "Started time synchronization service: ${service}."
            return 0
        fi
    done
    return 1
}

# Configure automatic clock synchronization using the platform's available daemon.
configure_time_synchronization() {
    if has_cmd systemctl; then
        enable_systemd_time_service || true
    else
        enable_legacy_time_service || true
    fi

    if [[ -z "$TIME_SYNC_SERVICE" ]]; then
        log "No supported time synchronization service was found; leaving the current clock configuration unchanged."
        return 0
    fi

    if has_cmd timedatectl; then
        timedatectl set-ntp true >/dev/null 2>&1 || true
        log "Automatic NTP synchronization is enabled."
    fi

    if has_cmd chronyc && [[ "$TIME_SYNC_SERVICE" == chrony* ]]; then
        chronyc -a makestep >/dev/null 2>&1 || true
    fi
}

main() {
    configure_time_synchronization
}

main "$@"
