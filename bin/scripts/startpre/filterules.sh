#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Apply one filter rule table from SQLite.
apply_filter_table() {
    local db_path="$1"
    local command="$2"
    local family="$3"
    local table_name="$4"
    local chain="$5"
    local iface_in_expr iface_out_expr
    local row
    local id rule_order iface_in iface_out ct_new ct_established ct_related ct_invalid
    local src_addr src_port dst_addr dst_port protocol protocol_type protocol_code action
    local -a spec

    [[ -f "$db_path" ]] || return 0
    sqlite_table_exists "$db_path" "$table_name" || return 0
    ensure_pending_delete_column "$db_path" "$table_name"

    case "$chain" in
        INPUT) iface_in_expr="COALESCE(iface_in, '')"; iface_out_expr="''" ;;
        OUTPUT) iface_in_expr="''"; iface_out_expr="COALESCE(iface_out, '')" ;;
        *) iface_in_expr="COALESCE(iface_in, '')"; iface_out_expr="COALESCE(iface_out, '')" ;;
    esac

    while IFS="$SQLITE_QUERY_SEPARATOR" read -r id rule_order iface_in iface_out ct_new ct_established ct_related ct_invalid src_addr src_port dst_addr dst_port protocol protocol_type protocol_code action; do
        [[ -n "${id:-}" ]] || continue
        spec=("$command" "-t" "filter" "$chain")
        add_interface_matches spec "$chain" "$iface_in" "$iface_out"
        add_address_match spec "-s" "$src_addr"
        add_address_match spec "-d" "$dst_addr"
        add_protocol_match spec "$family" "$protocol" "$protocol_type" "$protocol_code" "$src_port" "$dst_port"
        add_conntrack_match spec "$ct_new" "$ct_established" "$ct_related" "$ct_invalid"
        spec+=("-j" "${action:-ACCEPT}")
        apply_iptables_rule "${spec[@]}"
    done < <(
        sqlite_query "$db_path" "
            SELECT id, rule_order, ${iface_in_expr}, ${iface_out_expr},
                   COALESCE(ct_new, 0), COALESCE(ct_established, 0), COALESCE(ct_related, 0), COALESCE(ct_invalid, 0),
                   COALESCE(src_addr, ''), COALESCE(src_port, ''), COALESCE(dst_addr, ''), COALESCE(dst_port, ''),
                   COALESCE(protocol_name, 'all'), COALESCE(protocol_type, ''), COALESCE(protocol_code, ''),
                   COALESCE(action, 'ACCEPT')
            FROM ${table_name}
            WHERE enabled = 1 AND COALESCE(pending_delete, 0) = 0
            ORDER BY rule_order, id;
        "
    )
}

# Apply filter policies from the filter rules database.
apply_filter_policies() {
    local db_path="$1"
    local command="$2"
    local chain policy

    [[ -f "$db_path" ]] || return 0
    sqlite_table_exists "$db_path" "filter_chain_policies" || return 0

    for chain in INPUT FORWARD OUTPUT; do
        policy="$(sqlite_query "$db_path" "SELECT policy FROM filter_chain_policies WHERE chain_name=$(sql_quote "$chain") LIMIT 1;")"
        [[ -n "$policy" ]] || {
            [[ "$chain" == "OUTPUT" ]] && policy="ACCEPT" || policy="DROP"
        }
        [[ "$policy" == "ACCEPT" || "$policy" == "DROP" ]] || policy="DROP"
        "$command" -t filter -P "$chain" "$policy"
    done
}

# Apply all persisted IPv4 and IPv6 filter rules.
main() {
    local ipv4_filter_db ipv6_filter_db

    log "Applying persisted filter rules."

    ipv4_filter_db="$(filter_db_for_family ipv4)"
    ipv6_filter_db="$(filter_db_for_family ipv6)"

    if has_cmd iptables; then
        apply_filter_table "$ipv4_filter_db" iptables ipv4 filter_input_rules INPUT
        apply_filter_table "$ipv4_filter_db" iptables ipv4 filter_forward_rules FORWARD
        apply_filter_table "$ipv4_filter_db" iptables ipv4 filter_output_rules OUTPUT
        apply_filter_policies "$ipv4_filter_db" iptables
    fi

    if has_cmd ip6tables; then
        apply_filter_table "$ipv6_filter_db" ip6tables ipv6 filter_input_rules INPUT
        apply_filter_table "$ipv6_filter_db" ip6tables ipv6 filter_forward_rules FORWARD
        apply_filter_table "$ipv6_filter_db" ip6tables ipv6 filter_output_rules OUTPUT
        apply_filter_policies "$ipv6_filter_db" ip6tables
    fi
}

main "$@"
