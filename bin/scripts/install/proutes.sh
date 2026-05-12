#!/usr/bin/env bash

POLICY_ROUTING_DB="${POLICY_ROUTING_DB:-$ROOT_DIR/db/policy-routing.db}"
RT_TABLES_PATH="${RT_TABLES_PATH:-/etc/iproute2/rt_tables}"

# Return a SQL-safe quoted string or NULL for empty values.
policy_sql_value() {
    local value="${1:-}"

    if [[ -z "$value" ]]; then
        printf 'NULL'
        return 0
    fi

    value="${value//\'/\'\'}"
    printf "'%s'" "$value"
}

# Return a SQL-safe numeric value or NULL for empty values.
policy_sql_number() {
    local value="${1:-}"

    if [[ "$value" =~ ^[0-9]+$ ]]; then
        printf '%s' "$value"
    else
        printf 'NULL'
    fi
}

# Ensure the iproute2 routing table registry exists with the built-in table names.
ensure_rt_tables_file() {
    local rt_dir

    rt_dir="$(dirname "$RT_TABLES_PATH")"
    mkdir -p "$rt_dir" || fatal "Could not create iproute2 configuration directory: ${rt_dir}."
    touch "$RT_TABLES_PATH" || fatal "Could not create iproute2 routing table registry: ${RT_TABLES_PATH}."

    ensure_rt_table_entry 255 local
    ensure_rt_table_entry 254 main
    ensure_rt_table_entry 253 default
}

# Ensure one table id/name mapping exists in rt_tables.
ensure_rt_table_entry() {
    local table_id="$1"
    local table_name="$2"
    local temp_file

    temp_file="$(mktemp "${RT_TABLES_PATH}.XXXXXX")" || fatal "Could not allocate temporary rt_tables file."
    awk -v id="$table_id" -v name="$table_name" '
        BEGIN { added = 0 }
        /^[[:space:]]*#/ || NF < 2 {
            print
            next
        }
        $1 == id || $2 == name {
            if (!added) {
                printf "%s\t%s\n", id, name
                added = 1
            }
            next
        }
        { print }
        END {
            if (!added) {
                printf "%s\t%s\n", id, name
            }
        }
    ' "$RT_TABLES_PATH" > "$temp_file" || {
        rm -f "$temp_file"
        fatal "Could not update iproute2 routing table registry: ${RT_TABLES_PATH}."
    }
    mv "$temp_file" "$RT_TABLES_PATH" || fatal "Could not replace iproute2 routing table registry: ${RT_TABLES_PATH}."
}

# Rewrite rt_tables with every enabled table currently persisted in SQLite.
sync_rt_tables_from_db() {
    local rt_dir
    local temp_file

    rt_dir="$(dirname "$RT_TABLES_PATH")"
    mkdir -p "$rt_dir" || fatal "Could not create iproute2 configuration directory: ${rt_dir}."
    temp_file="$(mktemp "${RT_TABLES_PATH}.XXXXXX")" || fatal "Could not allocate temporary rt_tables file."

    {
        printf '# ArmFirewall managed iproute2 routing tables.\n'
        printf '255\tlocal\n'
        printf '254\tmain\n'
        printf '253\tdefault\n'
        printf '0\tunspec\n'
        sqlite3 -separator '|' "$POLICY_ROUTING_DB" "
            SELECT table_id, table_name
            FROM routing_tables
            WHERE enabled = 1
              AND pending_delete = 0
              AND table_id NOT IN (0, 253, 254, 255)
            ORDER BY
                table_id;
        " | awk -F'|' 'NF >= 2 { printf "%s\t%s\n", $1, $2 }'
    } > "$temp_file" || {
        rm -f "$temp_file"
        fatal "Could not render iproute2 routing table registry from SQLite."
    }

    mv "$temp_file" "$RT_TABLES_PATH" || fatal "Could not replace iproute2 routing table registry: ${RT_TABLES_PATH}."
}

# Return the LAN interface persisted by install.sh.
configured_lan_iface() {
    [[ -f "$IFACE_DB" ]] || return 0
    sqlite3 -noheader "$IFACE_DB" "
        SELECT name
        FROM ifaces
        WHERE role = 'LAN'
          AND protected = 1
        ORDER BY id
        LIMIT 1;
    "
}

# Return success when a route is the connected network for the configured LAN interface.
route_is_configured_lan_network() {
    local family="$1"
    local destination="$2"
    local dev="$3"
    local lan_iface
    local ip_family
    local line
    local prefix

    lan_iface="$(configured_lan_iface)"
    [[ -n "$lan_iface" && "$dev" == "$lan_iface" ]] || return 1
    [[ -n "$destination" && "$destination" != "default" ]] || return 1

    case "$family" in
        ipv4)
            ip_family="-4"
            ;;
        ipv6)
            ip_family="-6"
            ;;
        *)
            return 1
            ;;
    esac

    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        prefix="${line%% *}"
        [[ "$prefix" == "$destination" ]] && return 0
    done < <(ip "$ip_family" route show dev "$lan_iface" 2>/dev/null || true)

    return 1
}

# Verify that execddl.sh already created the policy routing database.
require_policy_routing_db() {
    command -v sqlite3 >/dev/null 2>&1 || fatal "sqlite3 is required to store policy routing data."
    [[ -f "$POLICY_ROUTING_DB" ]] || \
        fatal "Policy routing database was not found: ${POLICY_ROUTING_DB}. Run bin/scripts/install/execddl.sh first."

    sqlite3 "$POLICY_ROUTING_DB" "
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name IN ('routing_tables', 'routes', 'routing_rules')
        GROUP BY 1
        HAVING COUNT(*) = 3;
    " | grep -qx '1' || fatal "Policy routing database schema is incomplete: ${POLICY_ROUTING_DB}."

    ensure_policy_routing_apply_columns
}

# Execute SQL against the policy routing SQLite database.
policy_sqlite_exec() {
    local sql="$1"

    sqlite3 "$POLICY_ROUTING_DB" "$sql" || fatal "Could not update policy routing database: ${POLICY_ROUTING_DB}."
}

# Add apply-state columns to policy routing databases created before this field existed.
ensure_policy_routing_apply_columns() {
    local table

    for table in routing_tables routes routing_rules; do
        if ! sqlite3 "$POLICY_ROUTING_DB" "PRAGMA table_info(${table});" | awk -F'|' '$2 == "applied" { found = 1 } END { exit found ? 0 : 1 }'; then
            policy_sqlite_exec "ALTER TABLE ${table} ADD COLUMN applied INTEGER NOT NULL DEFAULT 0;"
        fi
    done
}

# Return the numeric id for a named Linux routing table.
route_table_id_for_name() {
    local table_name="$1"
    local table_id=""

    case "$table_name" in
        local)
            printf '255\n'
            return 0
            ;;
        main|"")
            printf '254\n'
            return 0
            ;;
        default)
            printf '253\n'
            return 0
            ;;
    esac

    if [[ "$table_name" =~ ^[0-9]+$ ]]; then
        printf '%s\n' "$table_name"
        return 0
    fi

    if [[ -r "$RT_TABLES_PATH" ]]; then
        table_id="$(awk -v name="$table_name" '$1 !~ /^#/ && $2 == name { print $1; exit }' "$RT_TABLES_PATH")"
    fi

    [[ -n "$table_id" ]] || table_id="254"
    printf '%s\n' "$table_id"
}

# Return the canonical name for a numeric Linux routing table.
route_table_name_for_id() {
    local table_id="$1"
    local table_name=""

    case "$table_id" in
        255)
            printf 'local\n'
            return 0
            ;;
        254)
            printf 'main\n'
            return 0
            ;;
        253)
            printf 'default\n'
            return 0
            ;;
    esac

    if [[ -r "$RT_TABLES_PATH" ]]; then
        table_name="$(awk -v id="$table_id" '$1 !~ /^#/ && $1 == id { print $2; exit }' "$RT_TABLES_PATH")"
    fi

    [[ -n "$table_name" ]] || table_name="table_${table_id}"
    printf '%s\n' "$table_name"
}

# Store one routing table definition.
record_routing_table() {
    local table_id="$1"
    local table_name="$2"
    local protected="${3:-0}"

    policy_sqlite_exec "
        INSERT INTO routing_tables (
            table_id, table_name, description, protected, enabled, applied, pending_delete,
            created_at, updated_at
        ) VALUES (
            ${table_id}, $(policy_sql_value "$table_name"), 'Imported from Linux iproute2 state.',
            ${protected}, 1, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT(table_id) DO UPDATE SET
            table_name = excluded.table_name,
            protected = CASE WHEN routing_tables.protected = 1 THEN 1 ELSE excluded.protected END,
            enabled = 1,
            applied = 1,
            pending_delete = 0,
            updated_at = CURRENT_TIMESTAMP;
    "
}

# Import Linux routing table names from rt_tables.
import_route_table_names() {
    local table_id table_name protected

    record_routing_table 255 local 1
    record_routing_table 254 main 1
    record_routing_table 253 default 1

    [[ -r "$RT_TABLES_PATH" ]] || return 0

    while read -r table_id table_name _; do
        [[ -n "${table_id:-}" && -n "${table_name:-}" ]] || continue
        [[ "$table_id" =~ ^# ]] && continue
        [[ "$table_id" =~ ^[0-9]+$ ]] || continue
        (( table_id > 0 )) || continue
        protected=0
        [[ "$table_id" =~ ^(255|254|253)$ ]] && protected=1
        record_routing_table "$table_id" "$table_name" "$protected"
    done < "$RT_TABLES_PATH"
}

# Reset imported route and rule rows before reading the current operating system state.
clear_imported_policy_routing_state() {
    policy_sqlite_exec "
        PRAGMA foreign_keys = ON;
        DELETE FROM route_nexthops;
        DELETE FROM routes;
        DELETE FROM routing_rules;
        UPDATE routing_tables
        SET enabled = 1,
            applied = 1,
            pending_delete = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE protected = 1;
    "
}

# Return a normalized route type.
normalize_route_type() {
    local value="$1"

    case "$value" in
        local|broadcast|multicast|throw|unreachable|prohibit|blackhole|anycast)
            printf '%s\n' "$value"
            ;;
        *)
            printf 'unicast\n'
            ;;
    esac
}

# Return a protocol only when it is accepted by the policy routing schema.
normalize_route_protocol() {
    local value="$1"

    case "$value" in
        redirect|kernel|boot|static|ra|dhcp|mrouted|babel|bird|bootp|dhcpv6|dnrouted|eigrp|gated|isis|keepalived|mrt|ntk|ospf|rip|unspec|xorp|zebra)
            printf '%s\n' "$value"
            ;;
        *)
            printf '\n'
            ;;
    esac
}

# Return a scope only when it is accepted by the policy routing schema.
normalize_route_scope() {
    local value="$1"

    case "$value" in
        global|site|link|host|nowhere)
            printf '%s\n' "$value"
            ;;
        *)
            printf '\n'
            ;;
    esac
}

# Store one parsed route from ip route output.
record_route_row() {
    local family="$1"
    local route_order="$2"
    local route_type="$3"
    local destination="$4"
    local table_id="$5"
    local gateway="$6"
    local dev="$7"
    local preferred_source="$8"
    local metric="$9"
    local scope="${10}"
    local protocol="${11}"
    local onlink="${12}"
    local table_name
    local protected=0

    table_name="$(route_table_name_for_id "$table_id")"
    record_routing_table "$table_id" "$table_name" "$([[ "$table_id" =~ ^(255|254|253)$ ]] && printf 1 || printf 0)"

    if [[ "$table_id" =~ ^(253|255)$ || "$protocol" == "kernel" || "$route_type" =~ ^(local|broadcast|multicast)$ ]] || \
        route_is_configured_lan_network "$family" "$destination" "$dev"; then
        protected=1
    fi

    policy_sqlite_exec "
        INSERT INTO routes (
            route_order, addr_family, table_id, route_type, destination,
            gateway, dev, preferred_source, metric, scope, protocol, onlink,
            protected, enabled, applied, pending_delete, created_at, updated_at
        ) VALUES (
            ${route_order}, $(policy_sql_value "$family"), ${table_id},
            $(policy_sql_value "$route_type"), $(policy_sql_value "$destination"),
            $(policy_sql_value "$gateway"), $(policy_sql_value "$dev"),
            $(policy_sql_value "$preferred_source"), $(policy_sql_number "$metric"),
            $(policy_sql_value "$scope"), $(policy_sql_value "$protocol"), ${onlink},
            ${protected}, 1, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
    "
}

# Parse and import one route line emitted by ip route show table all.
import_route_line() {
    local family="$1"
    local route_order="$2"
    local line="$3"
    local -a tokens
    local idx=0
    local route_type="unicast"
    local destination="default"
    local table_name="main"
    local table_id
    local gateway=""
    local dev=""
    local preferred_source=""
    local metric=""
    local scope=""
    local protocol=""
    local onlink=0

    read -r -a tokens <<< "$line"
    [[ "${#tokens[@]}" -gt 0 ]] || return 0

    route_type="$(normalize_route_type "${tokens[0]}")"
    if [[ "$route_type" == "unicast" ]]; then
        destination="${tokens[0]}"
        idx=1
    else
        destination="${tokens[1]:-default}"
        idx=2
    fi

    while (( idx < ${#tokens[@]} )); do
        case "${tokens[$idx]}" in
            via)
                gateway="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            dev)
                dev="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            table)
                table_name="${tokens[$((idx + 1))]:-main}"
                idx=$((idx + 2))
                ;;
            proto)
                protocol="$(normalize_route_protocol "${tokens[$((idx + 1))]:-}")"
                idx=$((idx + 2))
                ;;
            scope)
                scope="$(normalize_route_scope "${tokens[$((idx + 1))]:-}")"
                idx=$((idx + 2))
                ;;
            src)
                preferred_source="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            metric)
                metric="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            onlink)
                onlink=1
                idx=$((idx + 1))
                ;;
            *)
                idx=$((idx + 1))
                ;;
        esac
    done

    table_id="$(route_table_id_for_name "$table_name")"
    record_route_row "$family" "$route_order" "$route_type" "$destination" "$table_id" \
        "$gateway" "$dev" "$preferred_source" "$metric" "$scope" "$protocol" "$onlink"
}

# Import all IPv4 and IPv6 routes from the operating system.
import_routes_for_family() {
    local family="$1"
    local ip_family="$2"
    local line
    local route_order=1

    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        import_route_line "$family" "$route_order" "$line"
        route_order=$((route_order + 1))
    done < <(ip "$ip_family" route show table all 2>/dev/null || true)
}

# Store one parsed policy routing rule.
record_rule_row() {
    local family="$1"
    local rule_order="$2"
    local priority="$3"
    local source_addr="$4"
    local destination_addr="$5"
    local incoming_iface="$6"
    local outgoing_iface="$7"
    local fwmark="$8"
    local fwmask="$9"
    local tos="${10}"
    local ip_proto="${11}"
    local sport="${12}"
    local dport="${13}"
    local uid_range="${14}"
    local action="${15}"
    local table_id="${16}"
    local protected=0

    if [[ "$priority" =~ ^(0|32766|32767)$ ]]; then
        protected=1
    fi

    policy_sqlite_exec "
        INSERT INTO routing_rules (
            rule_order, addr_family, priority, source_addr, destination_addr,
            incoming_iface, outgoing_iface, fwmark, fwmask, tos, ip_proto,
            sport, dport, uid_range, action, table_id, protected, enabled,
            applied, pending_delete, created_at, updated_at
        ) VALUES (
            ${rule_order}, $(policy_sql_value "$family"), ${priority},
            $(policy_sql_value "$source_addr"), $(policy_sql_value "$destination_addr"),
            $(policy_sql_value "$incoming_iface"), $(policy_sql_value "$outgoing_iface"),
            $(policy_sql_value "$fwmark"), $(policy_sql_value "$fwmask"),
            $(policy_sql_value "$tos"), $(policy_sql_value "$ip_proto"),
            $(policy_sql_value "$sport"), $(policy_sql_value "$dport"),
            $(policy_sql_value "$uid_range"), $(policy_sql_value "$action"),
            $(policy_sql_number "$table_id"), ${protected}, 1, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
    "
}

# Parse and import one rule line emitted by ip rule show.
import_rule_line() {
    local family="$1"
    local rule_order="$2"
    local line="$3"
    local priority
    local rest
    local -a tokens
    local idx=0
    local source_addr=""
    local destination_addr=""
    local incoming_iface=""
    local outgoing_iface=""
    local fwmark=""
    local fwmask=""
    local tos=""
    local ip_proto=""
    local sport=""
    local dport=""
    local uid_range=""
    local action="lookup"
    local table_name=""
    local table_id=""

    priority="${line%%:*}"
    rest="${line#*:}"
    rest="${rest#"${rest%%[![:space:]]*}"}"
    [[ "$priority" =~ ^[0-9]+$ ]] || return 0

    read -r -a tokens <<< "$rest"
    while (( idx < ${#tokens[@]} )); do
        case "${tokens[$idx]}" in
            from)
                source_addr="${tokens[$((idx + 1))]:-}"
                [[ "$source_addr" == "all" ]] && source_addr=""
                idx=$((idx + 2))
                ;;
            to)
                destination_addr="${tokens[$((idx + 1))]:-}"
                [[ "$destination_addr" == "all" ]] && destination_addr=""
                idx=$((idx + 2))
                ;;
            iif)
                incoming_iface="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            oif)
                outgoing_iface="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            fwmark)
                fwmark="${tokens[$((idx + 1))]:-}"
                if [[ "$fwmark" == */* ]]; then
                    fwmask="${fwmark#*/}"
                    fwmark="${fwmark%%/*}"
                fi
                idx=$((idx + 2))
                ;;
            tos|dsfield)
                tos="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            ipproto)
                ip_proto="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            sport)
                sport="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            dport)
                dport="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            uidrange)
                uid_range="${tokens[$((idx + 1))]:-}"
                idx=$((idx + 2))
                ;;
            lookup|table)
                action="lookup"
                table_name="${tokens[$((idx + 1))]:-main}"
                idx=$((idx + 2))
                ;;
            blackhole|unreachable|prohibit)
                action="${tokens[$idx]}"
                table_name=""
                idx=$((idx + 1))
                ;;
            *)
                idx=$((idx + 1))
                ;;
        esac
    done

    if [[ "$action" == "lookup" ]]; then
        table_id="$(route_table_id_for_name "$table_name")"
        record_routing_table "$table_id" "$(route_table_name_for_id "$table_id")" "$([[ "$table_id" =~ ^(255|254|253)$ ]] && printf 1 || printf 0)"
    fi

    record_rule_row "$family" "$rule_order" "$priority" "$source_addr" "$destination_addr" \
        "$incoming_iface" "$outgoing_iface" "$fwmark" "$fwmask" "$tos" "$ip_proto" \
        "$sport" "$dport" "$uid_range" "$action" "$table_id"
}

# Import all IPv4 and IPv6 policy routing rules from the operating system.
import_rules_for_family() {
    local family="$1"
    local ip_family="$2"
    local line
    local rule_order=1

    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        import_rule_line "$family" "$rule_order" "$line"
        rule_order=$((rule_order + 1))
    done < <(ip "$ip_family" rule show 2>/dev/null || true)
}

# Synchronize the policy routing SQLite database with the current Linux state.
sync_policy_routing_db() {
    log "Synchronizing Linux policy routing state into ${POLICY_ROUTING_DB}."
    require_policy_routing_db
    sync_rt_tables_from_db
    clear_imported_policy_routing_state
    import_route_table_names
    import_routes_for_family ipv4 -4
    import_routes_for_family ipv6 -6
    import_rules_for_family ipv4 -4
    import_rules_for_family ipv6 -6
    log "Policy routing database synchronization completed."
}
