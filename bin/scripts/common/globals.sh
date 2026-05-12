#!/usr/bin/env bash
set -Eeuo pipefail

# Resolves the ArmFirewall project root directory from the current 
# script location
resolve_root_dir() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd
}

# Global Variables
export ROOT_DIR="$(resolve_root_dir)"

# shellcheck source=../common/log.sh
. "$ROOT_DIR/bin/scripts/common/log.sh"

export ARMFIREWALL_LOG_CONTEXT="$(basename "$0")"
export CONF_DIR="$ROOT_DIR/conf"
export DB_DIR="$ROOT_DIR/db"
export IFACE_DB="$DB_DIR/iface.db"
export PROC_DB="${PROC_DB:-$DB_DIR/proc.db}"
export POLICY_ROUTING_DB="${POLICY_ROUTING_DB:-$DB_DIR/policy-routing.db}"
export LAN_IFACE="${LAN_IFACE:-}"
export WAN_IFACE="${WAN_IFACE:-}"
export ROUTER_MODE="${ROUTER_MODE:-0}"
export IPV4_FILTER_RULES_DB="${IPV4_FILTER_RULES_DB:-$DB_DIR/ipv4-filter-rules.db}"
export IPV6_FILTER_RULES_DB="${IPV6_FILTER_RULES_DB:-$DB_DIR/ipv6-filter-rules.db}"
export IPV4_NAT_RULES_DB="${IPV4_NAT_RULES_DB:-$DB_DIR/ipv4-nat-rules.db}"
export IPV6_NAT_RULES_DB="${IPV6_NAT_RULES_DB:-$DB_DIR/ipv6-nat-rules.db}"
export IPV4_MANGLE_RULES_DB="${IPV4_MANGLE_RULES_DB:-$DB_DIR/ipv4-mangle-rules.db}"
export IPV6_MANGLE_RULES_DB="${IPV6_MANGLE_RULES_DB:-$DB_DIR/ipv6-mangle-rules.db}"
export IPV4_FILTER_DB="${IPV4_FILTER_DB:-$IPV4_FILTER_RULES_DB}"
export IPV6_FILTER_DB="${IPV6_FILTER_DB:-$IPV6_FILTER_RULES_DB}"
export IPV4_FILTER_FALLBACK_DB="${IPV4_FILTER_FALLBACK_DB:-$DB_DIR/ipv4-firewall-rules.db}"
export IPV6_FILTER_FALLBACK_DB="${IPV6_FILTER_FALLBACK_DB:-$DB_DIR/ipv6-firewall-rules.db}"
export IPV4_NAT_DB="${IPV4_NAT_DB:-$IPV4_NAT_RULES_DB}"
export IPV6_NAT_DB="${IPV6_NAT_DB:-$IPV6_NAT_RULES_DB}"
export IPV4_MANGLE_DB="${IPV4_MANGLE_DB:-$IPV4_MANGLE_RULES_DB}"
export IPV6_MANGLE_DB="${IPV6_MANGLE_DB:-$IPV6_MANGLE_RULES_DB}"
export RT_TABLES_PATH="${RT_TABLES_PATH:-/etc/iproute2/rt_tables}"
export SUPERVISORD_CONF="$CONF_DIR/supervisord.conf"
export PKG_MANAGER=""
export ALLOW_LAN_TCP_PORTS=(22 8000 53)
export ALLOW_LAN_UDP_PORTS=(67 53)
export SQLITE_QUERY_SEPARATOR=$'\037'

# Print the ArmFirewall execution banner.
print_banner() {
    local mode="${1:-runtime}"

    cat <<BANNER
   ___                    ______ _                        _ _
  / _ \\                   |  ___(_)                      | | |
 / /_\\ \\ _ __  _ __ ___   | |_   _ _ __ _____      ____ _| | |
 |  _  || '__|| '_ \` _ \\  |  _| | | '__/ _ \\ \\ /\\ / / _\` | | |
 | | | || |   | | | | | | | |   | | | |  __/\\ V  V / (_| | | |
 \\_| |_/\\_|   |_| |_| |_| \\_|   |_|_|  \\___| \\_/\\_/ \\__,_|_|_|

        ./ ArmFirewall ${mode}
        secure edge routing / firewall / monitoring
BANNER
}

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

# Return whether the given network interface is currently active.
net_iface_active_flag() {
    local iface="$1"

    [[ "$(cat "/sys/class/net/${iface}/operstate" 2>/dev/null || true)" == "up" ]] && printf '1\n' || printf '0\n'
}

# Return the MTU configured for the given network interface.
net_iface_mtu() {
    local iface="$1"

    cat "/sys/class/net/${iface}/mtu" 2>/dev/null || printf '0\n'
}

# Return the MAC address configured for the given network interface.
net_iface_mac() {
    local iface="$1"

    cat "/sys/class/net/${iface}/address" 2>/dev/null || printf '\n'
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

# Execute a SQLite query using tab-separated output.
sqlite_query() {
    local db_path="$1"
    local sql="$2"

    [[ -f "$db_path" ]] || return 0
    sqlite3 -noheader -separator "$SQLITE_QUERY_SEPARATOR" "$db_path" "$sql"
}

# Return whether one table exists in a SQLite database.
sqlite_table_exists() {
    local db_path="$1"
    local table_name="$2"
    local found

    [[ -f "$db_path" ]] || return 1
    found="$(sqlite3 -noheader "$db_path" "SELECT name FROM sqlite_master WHERE type='table' AND name=$(sql_quote "$table_name") LIMIT 1;")"
    [[ "$found" == "$table_name" ]]
}

# Add pending_delete to older rule tables when the column is missing.
ensure_pending_delete_column() {
    local db_path="$1"
    local table_name="$2"
    local found

    sqlite_table_exists "$db_path" "$table_name" || return 0
    found="$(sqlite_query "$db_path" "PRAGMA table_info(${table_name});" | awk -F"$SQLITE_QUERY_SEPARATOR" '$2 == "pending_delete" { print $2; exit }')"
    [[ "$found" == "pending_delete" ]] && return 0

    sqlite_exec "$db_path" "ALTER TABLE ${table_name} ADD COLUMN pending_delete INTEGER NOT NULL DEFAULT 0;"
}

# Return the available filter rules database while old installations are migrated.
filter_db_for_family() {
    local family="$1"
    local preferred fallback

    if [[ "$family" == "ipv6" ]]; then
        preferred="$IPV6_FILTER_DB"
        fallback="$IPV6_FILTER_FALLBACK_DB"
    else
        preferred="$IPV4_FILTER_DB"
        fallback="$IPV4_FILTER_FALLBACK_DB"
    fi

    [[ -f "$preferred" ]] && printf '%s\n' "$preferred" && return 0
    [[ -f "$fallback" ]] && printf '%s\n' "$fallback" && return 0
    printf '%s\n' "$preferred"
}

# Append one argument pair when the value is present.
add_if_value() {
    local -n command_ref="$1"
    local flag="$2"
    local value="${3:-}"

    [[ -n "$value" ]] && command_ref+=("$flag" "$value")
    return 0
}

# Append one address match when the value is not a wildcard.
add_address_match() {
    local -n command_ref="$1"
    local flag="$2"
    local value="${3:-}"

    case "$value" in
        ""|"0.0.0.0/0"|"::/0") return 0 ;;
    esac
    command_ref+=("$flag" "$value")
}

# Return whether a port value should be added to an iptables command.
is_real_port() {
    local value="${1:-}"

    [[ -n "$value" && "$value" != "0" ]]
}

# Append protocol, port and ICMP matches to an iptables command.
add_protocol_match() {
    local -n command_ref="$1"
    local family="$2"
    local protocol="$3"
    local protocol_type="$4"
    local protocol_code="$5"
    local src_port="$6"
    local dst_port="$7"
    local iptables_protocol
    local icmp_value

    protocol="${protocol:-all}"
    [[ "$protocol" == "all" ]] && return 0

    iptables_protocol="$protocol"
    if [[ "$family" == "ipv6" && ( "$protocol" == "icmp" || "$protocol" == "icmpv6" ) ]]; then
        iptables_protocol="ipv6-icmp"
    fi

    command_ref+=("-p" "$iptables_protocol")

    if [[ "$protocol" == "tcp" || "$protocol" == "udp" ]]; then
        is_real_port "$src_port" && command_ref+=("--sport" "$src_port")
        is_real_port "$dst_port" && command_ref+=("--dport" "$dst_port")
        return 0
    fi

    if [[ "$protocol" == "icmp" || "$protocol" == "icmpv6" ]]; then
        [[ -n "$protocol_type" ]] || return 0
        icmp_value="$protocol_type"
        [[ -n "$protocol_code" ]] && icmp_value="${icmp_value}/${protocol_code}"
        [[ "$family" == "ipv6" ]] && command_ref+=("--icmpv6-type" "$icmp_value") || command_ref+=("--icmp-type" "$icmp_value")
    fi

    return 0
}

# Append conntrack state matches for filter and mangle rules.
add_conntrack_match() {
    local -n command_ref="$1"
    local ct_new="$2"
    local ct_established="$3"
    local ct_related="$4"
    local ct_invalid="$5"
    local states=()

    [[ "$ct_new" == "1" ]] && states+=("NEW")
    [[ "$ct_established" == "1" ]] && states+=("ESTABLISHED")
    [[ "$ct_related" == "1" ]] && states+=("RELATED")
    [[ "$ct_invalid" == "1" ]] && states+=("INVALID")
    [[ "${#states[@]}" -gt 0 ]] && command_ref+=("-m" "conntrack" "--ctstate" "$(IFS=,; printf '%s' "${states[*]}")")
    return 0
}

# Append input/output interface matches according to the selected chain.
add_interface_matches() {
    local -n command_ref="$1"
    local chain="$2"
    local iface_in="$3"
    local iface_out="$4"

    case "$chain" in
        INPUT|FORWARD|PREROUTING)
            [[ -n "$iface_in" ]] && command_ref+=("-i" "$iface_in")
            ;;
    esac
    case "$chain" in
        OUTPUT|FORWARD|POSTROUTING)
            [[ -n "$iface_out" ]] && command_ref+=("-o" "$iface_out")
            ;;
    esac
    return 0
}

# Apply one rule after checking whether it already exists.
apply_iptables_rule() {
    local -a spec=("$@")
    local -a check_cmd add_cmd

    check_cmd=("${spec[0]}" "${spec[1]}" "${spec[2]}" "-C" "${spec[@]:3}")
    add_cmd=("${spec[0]}" "${spec[1]}" "${spec[2]}" "-A" "${spec[@]:3}")
    "${check_cmd[@]}" >/dev/null 2>&1 && return 0
    "${add_cmd[@]}"
}
