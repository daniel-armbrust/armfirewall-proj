#!/usr/bin/env bash
set -Eeuo pipefail

# Resolves the ArmFirewall project root directory from the current 
# script location
resolve_root_dir() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

# Global Variables
export ROOT_DIR="$(resolve_root_dir)"

# shellcheck source=log.sh
. "$ROOT_DIR/bin/scripts/log.sh"

export ARMFIREWALL_LOG_CONTEXT="$(basename "$0")"
export CONF_DIR="$ROOT_DIR/conf"
export DB_DIR="$ROOT_DIR/db"
export IFACE_DB="$DB_DIR/iface.db"
export SUPERVISORD_CONF="$CONF_DIR/supervisord.conf"
export PKG_MANAGER=""
export ALLOW_LAN_TCP_PORTS=(22 8000 53)
export ALLOW_LAN_UDP_PORTS=(67 53)

# Ensure the script is running with root privileges.
need_root() { 
    [[ ${EUID:-$(id -u)} -eq 0 ]] || fatal "This script must be run as root."; 
}

# Check if the command exists
has_cmd() { 
    command -v "$1" >/dev/null 2>&1; 
}

# Runs a command while capturing its combined output for later error 
# analysis
capture_run() { 
    local f

    f="$(mktemp)"; 
    
    set +e; "$@" > >(tee "$f") 2>&1; local s=$?; set -e; LAST_LOG="$f"; return "$s"; 
}

# Synchronizes the system clock before package transactions to avoid 
# signature validation errors
sync_system_clock() {
    if has_cmd chronyc; then
        log "Synchronizing system clock with chrony before package transactions."
        chronyc makestep || true
    elif has_cmd timedatectl; then
        log "Enabling NTP before package transactions."
        timedatectl set-ntp true || true
    fi
}

# Return a SQL-safe quoted string.
sql_quote() {
    local value="${1//\'/\'\'}"

    printf "'%s'" "$value"
}

# Execute SQL against one SQLite database or stop the startup flow.
sqlite_exec() {
    local db_path="$1"
    local sql="$2"

    command -v sqlite3 >/dev/null 2>&1 || fatal "sqlite3 is required to store firewall rules."

    [[ -f "$db_path" ]] || fatal "SQLite database was not found: ${db_path}."

    sqlite3 "$db_path" "$sql" || fatal "Could not update SQLite database: ${db_path}."
}
