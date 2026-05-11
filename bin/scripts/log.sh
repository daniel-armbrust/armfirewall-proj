#!/usr/bin/env bash
# Shared logging helpers for ArmFirewall shell scripts.

armfirewall_log_context() {
    if [[ -n "${ARMFIREWALL_LOG_CONTEXT:-}" ]]; then
        printf '%s' "$ARMFIREWALL_LOG_CONTEXT"
    else
        basename "$0"
    fi
}

log_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log() {
    printf '[%s] [%s] %s\n' "$(log_timestamp)" "$(armfirewall_log_context)" "$*" >&2
}

log_info() {
    log "INFO: $*"
}

log_warn() {
    log "WARN: $*"
}

log_error() {
    log "ERROR: $*"
}

fatal() {
    log_error "$*"
    exit 1
}
