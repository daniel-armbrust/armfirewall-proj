#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Ensure the iproute2 table registry contains the base routing tables.
ensure_base_rt_tables() {
    local rt_tables="$RT_TABLES_PATH"

    mkdir -p "$(dirname "$rt_tables")"
    touch "$rt_tables"
    sed -i '/^[[:space:]]*0[[:space:]]\+unspec\([[:space:]]\|$\)/d;/^[[:space:]]*253[[:space:]]\+default\([[:space:]]\|$\)/d;/^[[:space:]]*254[[:space:]]\+main\([[:space:]]\|$\)/d;/^[[:space:]]*255[[:space:]]\+local\([[:space:]]\|$\)/d' "$rt_tables"
    {
        printf '0\tunspec\n'
        printf '253\tdefault\n'
        printf '254\tmain\n'
        printf '255\tlocal\n'
    } >> "$rt_tables"
}

# Persist one user routing table in /etc/iproute2/rt_tables.
apply_route_table() {
    local table_id="$1"
    local table_name="$2"
    local rt_tables="$RT_TABLES_PATH"

    sed -i "/^[[:space:]]*${table_id}[[:space:]]/d;/^[[:space:]]*[0-9]\+[[:space:]]\+${table_name}\([[:space:]]\|$\)/d" "$rt_tables"
    printf '%s\t%s\n' "$table_id" "$table_name" >> "$rt_tables"
}

# Build and execute one ip route replace command.
apply_policy_route() {
    local id family table_id route_type destination gateway dev preferred_source metric scope protocol onlink
    local -a command

    IFS="$SQLITE_QUERY_SEPARATOR" read -r id family table_id route_type destination gateway dev preferred_source metric scope protocol onlink <<< "$1"
    [[ -n "${id:-}" ]] || return 0
    command=(ip)
    [[ "$family" == "ipv6" ]] && command+=("-6") || command+=("-4")
    command+=("route" "replace")
    [[ -n "$route_type" && "$route_type" != "unicast" ]] && command+=("$route_type")
    command+=("${destination:-default}" "table" "$table_id")
    add_if_value command "via" "$gateway"
    add_if_value command "dev" "$dev"
    add_if_value command "src" "$preferred_source"
    add_if_value command "metric" "$metric"
    add_if_value command "scope" "$scope"
    add_if_value command "proto" "$protocol"
    [[ "$onlink" == "1" ]] && command+=("onlink")
    if ! "${command[@]}"; then
        log "Skipping persisted route id=${id}: could not apply the saved route specification."
    fi
}

# Build and execute one ip rule add command.
apply_policy_rule() {
    local id family priority source_addr destination_addr incoming_iface outgoing_iface fwmark fwmask
    local tos dsfield ip_proto sport dport uid_range action table_id suppress_prefixlength suppress_ifgroup realms goto_priority
    local mark
    local -a command delete_command

    IFS="$SQLITE_QUERY_SEPARATOR" read -r id family priority source_addr destination_addr incoming_iface outgoing_iface fwmark fwmask tos dsfield ip_proto sport dport uid_range action table_id suppress_prefixlength suppress_ifgroup realms goto_priority <<< "$1"
    [[ -n "${id:-}" ]] || return 0

    command=(ip)
    [[ "$family" == "ipv6" ]] && command+=("-6") || command+=("-4")
    command+=("rule" "add" "priority" "$priority")
    add_if_value command "from" "$source_addr"
    add_if_value command "to" "$destination_addr"
    add_if_value command "iif" "$incoming_iface"
    add_if_value command "oif" "$outgoing_iface"
    if [[ -n "$fwmark" ]]; then
        mark="$fwmark"
        [[ -n "$fwmask" ]] && mark="${mark}/${fwmask}"
        command+=("fwmark" "$mark")
    fi
    add_if_value command "tos" "${tos:-$dsfield}"
    add_if_value command "ipproto" "$ip_proto"
    add_if_value command "sport" "$sport"
    add_if_value command "dport" "$dport"
    add_if_value command "uidrange" "$uid_range"
    if [[ "${action:-lookup}" == "lookup" ]]; then
        command+=("lookup" "$table_id")
    else
        command+=("$action")
    fi
    add_if_value command "suppress_prefixlength" "$suppress_prefixlength"
    add_if_value command "suppress_ifgroup" "$suppress_ifgroup"
    add_if_value command "realms" "$realms"
    add_if_value command "goto" "$goto_priority"

    delete_command=("${command[@]}")
    delete_command[3]="del"
    while "${delete_command[@]}" >/dev/null 2>&1; do :; done
    if ! "${command[@]}"; then
        log "Skipping persisted routing rule id=${id}: could not apply the saved rule specification."
    fi
}

# Apply enabled policy routing tables, routes and rules stored in SQLite.
apply_policy_routing() {
    local row

    [[ -f "$POLICY_ROUTING_DB" ]] || {
        log "Skipping missing policy routing database: ${POLICY_ROUTING_DB}."
        return 0
    }
    has_cmd ip || {
        log "Skipping policy routing because ip command was not found."
        return 0
    }

    log "Applying persisted policy routing state."
    ensure_base_rt_tables

    while IFS="$SQLITE_QUERY_SEPARATOR" read -r _id table_id table_name; do
        [[ -n "${table_id:-}" && -n "$table_name" ]] || continue
        apply_route_table "$table_id" "$table_name"
    done < <(
        sqlite_query "$POLICY_ROUTING_DB" "
            SELECT id, table_id, table_name
            FROM routing_tables
            WHERE enabled = 1 AND protected = 0 AND COALESCE(pending_delete, 0) = 0
            ORDER BY table_id;
        "
    )

    while IFS= read -r row; do
        [[ -n "$row" ]] && apply_policy_route "$row"
    done < <(
        sqlite_query "$POLICY_ROUTING_DB" "
            SELECT id, addr_family, table_id, COALESCE(route_type, 'unicast'), COALESCE(destination, 'default'),
                   COALESCE(gateway, ''), COALESCE(dev, ''), COALESCE(preferred_source, ''),
                   COALESCE(metric, ''), COALESCE(scope, ''), COALESCE(protocol, ''), COALESCE(onlink, 0)
            FROM routes
            WHERE enabled = 1 AND protected = 0 AND COALESCE(pending_delete, 0) = 0
            ORDER BY addr_family, table_id, route_order, id;
        "
    )

    while IFS= read -r row; do
        [[ -n "$row" ]] && apply_policy_rule "$row"
    done < <(
        sqlite_query "$POLICY_ROUTING_DB" "
            SELECT id, addr_family, priority, COALESCE(source_addr, ''), COALESCE(destination_addr, ''),
                   COALESCE(incoming_iface, ''), COALESCE(outgoing_iface, ''), COALESCE(fwmark, ''),
                   COALESCE(fwmask, ''), COALESCE(tos, ''), COALESCE(dsfield, ''), COALESCE(ip_proto, ''),
                   COALESCE(sport, ''), COALESCE(dport, ''), COALESCE(uid_range, ''), COALESCE(action, 'lookup'),
                   COALESCE(table_id, ''), COALESCE(suppress_prefixlength, ''), COALESCE(suppress_ifgroup, ''),
                   COALESCE(realms, ''), COALESCE(goto_priority, '')
            FROM routing_rules
            WHERE enabled = 1 AND protected = 0 AND COALESCE(pending_delete, 0) = 0
            ORDER BY addr_family, priority, id;
        "
    )
}

# Apply persisted policy routing tables, routes and rules.
main() {
    apply_policy_routing
}

main "$@"
