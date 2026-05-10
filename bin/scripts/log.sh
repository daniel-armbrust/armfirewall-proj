#!/usr/bin/env bash
# Shared logging helpers for HomeFirewall shell scripts.

homefirewall_log_context() {
    if [[ -n "${HOMEFIREWALL_LOG_CONTEXT:-}" ]]; then
        printf '%s' "$HOMEFIREWALL_LOG_CONTEXT"
    else
        basename "$0"
    fi
}

log_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log() {
    printf '[%s] [%s] %s\n' "$(log_timestamp)" "$(homefirewall_log_context)" "$*" >&2
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
