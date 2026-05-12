#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Append mangle target options when the selected target requires them.
add_mangle_target_options() {
    local -n command_ref="$1"
    local action="$2"
    local mark_value="$3"
    local dscp_value="$4"
    local tos_value="$5"
    local ttl_value="$6"

    case "$action" in
        MARK) [[ -n "$mark_value" ]] && command_ref+=("--set-mark" "$mark_value") ;;
        CONNMARK) [[ -n "$mark_value" ]] && command_ref+=("--set-xmark" "$mark_value") ;;
        DSCP) [[ -n "$dscp_value" ]] && command_ref+=("--set-dscp" "$dscp_value") ;;
        TOS) [[ -n "$tos_value" ]] && command_ref+=("--set-tos" "$tos_value") ;;
        TTL) [[ -n "$ttl_value" ]] && command_ref+=("--ttl-set" "$ttl_value") ;;
    esac
    return 0
}

# Apply one mangle rule table from SQLite.
apply_mangle_table() {
    local db_path="$1"
    local command="$2"
    local family="$3"
    local table_name="$4"
    local chain="$5"
    local iface_in_expr iface_out_expr
    local id rule_order iface_in iface_out ct_new ct_established ct_related ct_invalid
    local src_addr src_port dst_addr dst_port protocol protocol_type protocol_code action
    local mark_value dscp_value tos_value ttl_value
    local -a spec

    [[ -f "$db_path" ]] || return 0
    sqlite_table_exists "$db_path" "$table_name" || return 0
    ensure_pending_delete_column "$db_path" "$table_name"

    case "$chain" in
        PREROUTING|INPUT) iface_in_expr="COALESCE(iface_in, '')"; iface_out_expr="''" ;;
        OUTPUT|POSTROUTING) iface_in_expr="''"; iface_out_expr="COALESCE(iface_out, '')" ;;
        *) iface_in_expr="COALESCE(iface_in, '')"; iface_out_expr="COALESCE(iface_out, '')" ;;
    esac

    while IFS=$'\t' read -r id rule_order iface_in iface_out ct_new ct_established ct_related ct_invalid src_addr src_port dst_addr dst_port protocol protocol_type protocol_code action mark_value dscp_value tos_value ttl_value; do
        [[ -n "${id:-}" ]] || continue
        spec=("$command" "-t" "mangle" "$chain")
        add_interface_matches spec "$chain" "$iface_in" "$iface_out"
        add_address_match spec "-s" "$src_addr"
        add_address_match spec "-d" "$dst_addr"
        add_protocol_match spec "$family" "$protocol" "$protocol_type" "$protocol_code" "$src_port" "$dst_port"
        add_conntrack_match spec "$ct_new" "$ct_established" "$ct_related" "$ct_invalid"
        spec+=("-j" "${action:-ACCEPT}")
        add_mangle_target_options spec "${action:-ACCEPT}" "$mark_value" "$dscp_value" "$tos_value" "$ttl_value"
        apply_iptables_rule "${spec[@]}"
    done < <(
        sqlite_query "$db_path" "
            SELECT id, rule_order, ${iface_in_expr}, ${iface_out_expr},
                   COALESCE(ct_new, 0), COALESCE(ct_established, 0), COALESCE(ct_related, 0), COALESCE(ct_invalid, 0),
                   COALESCE(src_addr, ''), COALESCE(src_port, ''), COALESCE(dst_addr, ''), COALESCE(dst_port, ''),
                   COALESCE(protocol_name, 'all'), COALESCE(protocol_type, ''), COALESCE(protocol_code, ''),
                   COALESCE(mangle_action, 'ACCEPT'), COALESCE(mark_value, ''), COALESCE(dscp_value, ''),
                   COALESCE(tos_value, ''), COALESCE(ttl_value, '')
            FROM ${table_name}
            WHERE enabled = 1 AND COALESCE(pending_delete, 0) = 0
            ORDER BY rule_order, id;
        "
    )
}

# Apply all persisted IPv4 and IPv6 mangle rules.
main() {
    log "Applying persisted mangle rules."

    if has_cmd iptables; then
        apply_mangle_table "$IPV4_MANGLE_DB" iptables ipv4 mangle_prerouting_rules PREROUTING
        apply_mangle_table "$IPV4_MANGLE_DB" iptables ipv4 mangle_input_rules INPUT
        apply_mangle_table "$IPV4_MANGLE_DB" iptables ipv4 mangle_forward_rules FORWARD
        apply_mangle_table "$IPV4_MANGLE_DB" iptables ipv4 mangle_output_rules OUTPUT
        apply_mangle_table "$IPV4_MANGLE_DB" iptables ipv4 mangle_postrouting_rules POSTROUTING
    fi

    if has_cmd ip6tables; then
        apply_mangle_table "$IPV6_MANGLE_DB" ip6tables ipv6 mangle_prerouting_rules PREROUTING
        apply_mangle_table "$IPV6_MANGLE_DB" ip6tables ipv6 mangle_input_rules INPUT
        apply_mangle_table "$IPV6_MANGLE_DB" ip6tables ipv6 mangle_forward_rules FORWARD
        apply_mangle_table "$IPV6_MANGLE_DB" ip6tables ipv6 mangle_output_rules OUTPUT
        apply_mangle_table "$IPV6_MANGLE_DB" ip6tables ipv6 mangle_postrouting_rules POSTROUTING
    fi
}

main "$@"
