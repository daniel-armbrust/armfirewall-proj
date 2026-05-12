#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Append NAT target options when the selected target requires them.
add_nat_target_options() {
    local -n command_ref="$1"
    local action="$2"
    local to_addr="$3"
    local to_port="$4"
    local value

    case "$action" in
        DNAT)
            [[ -n "$to_addr" ]] || return 0
            value="$to_addr"
            is_real_port "$to_port" && value="${value}:${to_port}"
            command_ref+=("--to-destination" "$value")
            ;;
        SNAT)
            [[ -n "$to_addr" ]] || return 0
            value="$to_addr"
            is_real_port "$to_port" && value="${value}:${to_port}"
            command_ref+=("--to-source" "$value")
            ;;
        REDIRECT)
            is_real_port "$to_port" && command_ref+=("--to-ports" "$to_port")
            ;;
    esac
    return 0
}

# Apply one NAT rule table from SQLite.
apply_nat_table() {
    local db_path="$1"
    local command="$2"
    local family="$3"
    local table_name="$4"
    local chain="$5"
    local iface_in_expr iface_out_expr
    local id rule_order iface_in iface_out src_addr src_port dst_addr dst_port
    local protocol protocol_type protocol_code action to_addr to_port
    local -a spec

    [[ -f "$db_path" ]] || return 0
    sqlite_table_exists "$db_path" "$table_name" || return 0
    ensure_pending_delete_column "$db_path" "$table_name"

    case "$chain" in
        PREROUTING|INPUT) iface_in_expr="COALESCE(iface_in, '')"; iface_out_expr="''" ;;
        OUTPUT|POSTROUTING) iface_in_expr="''"; iface_out_expr="COALESCE(iface_out, '')" ;;
        *) iface_in_expr="COALESCE(iface_in, '')"; iface_out_expr="COALESCE(iface_out, '')" ;;
    esac

    while IFS=$'\t' read -r id rule_order iface_in iface_out src_addr src_port dst_addr dst_port protocol protocol_type protocol_code action to_addr to_port; do
        [[ -n "${id:-}" ]] || continue
        spec=("$command" "-t" "nat" "$chain")
        add_interface_matches spec "$chain" "$iface_in" "$iface_out"
        add_address_match spec "-s" "$src_addr"
        add_address_match spec "-d" "$dst_addr"
        add_protocol_match spec "$family" "$protocol" "$protocol_type" "$protocol_code" "$src_port" "$dst_port"
        spec+=("-j" "${action:-ACCEPT}")
        add_nat_target_options spec "${action:-ACCEPT}" "$to_addr" "$to_port"
        apply_iptables_rule "${spec[@]}"
    done < <(
        sqlite_query "$db_path" "
            SELECT id, rule_order, ${iface_in_expr}, ${iface_out_expr},
                   COALESCE(src_addr, ''), COALESCE(src_port, ''), COALESCE(dst_addr, ''), COALESCE(dst_port, ''),
                   COALESCE(protocol_name, 'all'), COALESCE(protocol_type, ''), COALESCE(protocol_code, ''),
                   COALESCE(nat_action, 'ACCEPT'), COALESCE(to_addr, ''), COALESCE(to_port, '')
            FROM ${table_name}
            WHERE enabled = 1 AND COALESCE(pending_delete, 0) = 0
            ORDER BY rule_order, id;
        "
    )
}

# Apply all persisted IPv4 and IPv6 NAT rules.
main() {
    log "Applying persisted NAT rules."

    if has_cmd iptables; then
        apply_nat_table "$IPV4_NAT_DB" iptables ipv4 nat_prerouting_rules PREROUTING
        apply_nat_table "$IPV4_NAT_DB" iptables ipv4 nat_input_rules INPUT
        apply_nat_table "$IPV4_NAT_DB" iptables ipv4 nat_output_rules OUTPUT
        apply_nat_table "$IPV4_NAT_DB" iptables ipv4 nat_postrouting_rules POSTROUTING
    fi

    if has_cmd ip6tables; then
        apply_nat_table "$IPV6_NAT_DB" ip6tables ipv6 nat_prerouting_rules PREROUTING
        apply_nat_table "$IPV6_NAT_DB" ip6tables ipv6 nat_input_rules INPUT
        apply_nat_table "$IPV6_NAT_DB" ip6tables ipv6 nat_output_rules OUTPUT
        apply_nat_table "$IPV6_NAT_DB" ip6tables ipv6 nat_postrouting_rules POSTROUTING
    fi
}

main "$@"
