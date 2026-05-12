#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=scripts/globals.sh
. "$ROOT_DIR/bin/scripts/globals.sh"

IPV4_FILTER_RULES_DB="${IPV4_FILTER_RULES_DB:-$DB_DIR/ipv4-filter-rules.db}"
IPV6_FILTER_RULES_DB="${IPV6_FILTER_RULES_DB:-$DB_DIR/ipv6-filter-rules.db}"

# Return the SQLite database path for the selected IP family.
filter_rules_db() {
    local family="$1"

    case "$family" in
        ipv4) 
            printf '%s\n' "$IPV4_FILTER_RULES_DB" 
            ;;

        ipv6) 
            printf '%s\n' "$IPV6_FILTER_RULES_DB" 
            ;;
    esac
}

# Return the wildcard address for the selected IP family.
filter_any_addr() {
    local family="$1"

    case "$family" in
        ipv4) 
            printf '0.0.0.0/0\n' 
            ;;

        ipv6) 
            printf '::/0\n' 
            ;;
    esac
}

# Register one LAN INPUT allow rule in the selected filter rules database.
record_lan_input_rule() {
    local family="$1"
    local protocol="$2"
    local iface="$3"
    local port="$4"
    local db_path
    local any_addr

    db_path="$(filter_rules_db "$family")"
    any_addr="$(filter_any_addr "$family")"

    sqlite_exec "$db_path" "
        INSERT INTO filter_input_rules (
            iface_in, rule_order, ct_new, ct_established, ct_related,
            ct_invalid, src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code, action,
            protected, enabled, created_at, updated_at)
                SELECT
                    $(sql_quote "$iface"), (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_input_rules),
                    1, 0, 0, 0, $(sql_quote "$any_addr"), 0,
                    $(sql_quote "$any_addr"), ${port},
                    $(sql_quote "$protocol"), NULL, NULL,
                    'ACCEPT', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM filter_input_rules 
                        WHERE iface_in = $(sql_quote "$iface")
                            AND protocol_name = $(sql_quote "$protocol")
                            AND dst_port = ${port}
                            AND action = 'ACCEPT'
        );"
}

# Apply one LAN INPUT allow rule using iptables or ip6tables.
apply_lan_input_rule() {
    local binary="$1"
    local protocol="$2"
    local iface="$3"
    local port="$4"

    "$binary" -t filter -C INPUT -i "$iface" -p "$protocol" --dport "$port" -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null || \
    "$binary" -t filter -A INPUT -i "$iface" -p "$protocol" --dport "$port" -m conntrack --ctstate NEW -j ACCEPT
}

# Apply base conntrack rules required for replies and forwarded return traffic.
apply_conntrack_base_rules() {
    log "Applying base conntrack rules for INPUT and FORWARD."

    iptables -t filter -C INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
    iptables -t filter -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

    ip6tables -t filter -C INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
    ip6tables -t filter -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

    iptables -t filter -C FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
    iptables -t filter -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

    ip6tables -t filter -C FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
    ip6tables -t filter -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
}

# Record one INPUT conntrack return rule in SQLite.
record_input_conntrack_return_rule() {
    local family="$1"
    local db_path
    local any_addr

    db_path="$(filter_rules_db "$family")"
    any_addr="$(filter_any_addr "$family")"

    sqlite_exec "$db_path" "
        INSERT INTO filter_input_rules (
            iface_in, rule_order, ct_new, ct_established, ct_related,
            ct_invalid, src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code, action,
            protected, enabled, created_at, updated_at)
                SELECT
                    'ANY', (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_input_rules),
                    0, 1, 1, 0, $(sql_quote "$any_addr"), NULL,
                    $(sql_quote "$any_addr"), NULL,
                    'all', NULL, NULL,
                    'ACCEPT', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM filter_input_rules
                        WHERE iface_in = 'ANY'
                            AND protocol_name = 'all'
                            AND ct_established = 1
                            AND ct_related = 1
                            AND action = 'ACCEPT'
                            AND enabled = 1
                );"
}

# Record one FORWARD conntrack return rule in SQLite.
record_forward_conntrack_return_rule() {
    local family="$1"
    local db_path
    local any_addr

    db_path="$(filter_rules_db "$family")"
    any_addr="$(filter_any_addr "$family")"

    sqlite_exec "$db_path" "
        INSERT INTO filter_forward_rules (
            iface_in, iface_out, rule_order, ct_new, ct_established, ct_related,
            ct_invalid, src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code, action,
            protected, enabled, created_at, updated_at)
                SELECT
                    'ANY', 'ANY', (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_forward_rules),
                    0, 1, 1, 0, $(sql_quote "$any_addr"), NULL,
                    $(sql_quote "$any_addr"), NULL,
                    'all', NULL, NULL,
                    'ACCEPT', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM filter_forward_rules
                        WHERE iface_in = 'ANY'
                            AND iface_out = 'ANY'
                            AND protocol_name = 'all'
                            AND ct_established = 1
                            AND ct_related = 1
                            AND action = 'ACCEPT'
                            AND enabled = 1
                );"
}

# Record base conntrack INPUT and FORWARD return rules in SQLite.
record_conntrack_base_rules() {
    record_input_conntrack_return_rule ipv4
    record_input_conntrack_return_rule ipv6
    record_forward_conntrack_return_rule ipv4
    record_forward_conntrack_return_rule ipv6
}

# Apply one ICMPv6 INPUT rule.
apply_icmpv6_input_rule() {
    local src_addr="$1"
    local icmp_type="$2"
    local icmp_code="$3"

    ip6tables -t filter -C INPUT -s "$src_addr" -p ipv6-icmp --icmpv6-type "${icmp_type}/${icmp_code}" -j ACCEPT 2>/dev/null || \
    ip6tables -t filter -A INPUT -s "$src_addr" -p ipv6-icmp --icmpv6-type "${icmp_type}/${icmp_code}" -j ACCEPT
}

# Apply one ICMPv6 FORWARD rule.
apply_icmpv6_forward_rule() {
    local icmp_type="$1"
    local icmp_code="$2"

    ip6tables -t filter -C FORWARD -p ipv6-icmp --icmpv6-type "${icmp_type}/${icmp_code}" -j ACCEPT 2>/dev/null || \
    ip6tables -t filter -A FORWARD -p ipv6-icmp --icmpv6-type "${icmp_type}/${icmp_code}" -j ACCEPT
}

# Record one ICMPv6 INPUT rule in SQLite.
record_icmpv6_input_rule() {
    local src_addr="$1"
    local icmp_type="$2"
    local icmp_code="$3"

    sqlite_exec "$IPV6_FILTER_RULES_DB" "
        INSERT INTO filter_input_rules (
            iface_in, rule_order, ct_new, ct_established, ct_related,
            ct_invalid, src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code, action,
            protected, enabled, created_at, updated_at)
                SELECT
                    'ANY', (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_input_rules),
                    1, 0, 0, 0, $(sql_quote "$src_addr"), NULL,
                    '::/0', NULL,
                    'icmpv6', ${icmp_type}, ${icmp_code},
                    'ACCEPT', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM filter_input_rules
                        WHERE iface_in = 'ANY'
                            AND src_addr = $(sql_quote "$src_addr")
                            AND protocol_name = 'icmpv6'
                            AND protocol_type = ${icmp_type}
                            AND protocol_code = ${icmp_code}
                            AND action = 'ACCEPT'
                            AND enabled = 1
                );"
}

# Record one ICMPv6 FORWARD rule in SQLite.
record_icmpv6_forward_rule() {
    local icmp_type="$1"
    local icmp_code="$2"

    sqlite_exec "$IPV6_FILTER_RULES_DB" "
        INSERT INTO filter_forward_rules (
            iface_in, iface_out, rule_order, ct_new, ct_established, ct_related,
            ct_invalid, src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code, action,
            protected, enabled, created_at, updated_at)
                SELECT
                    'ANY', 'ANY', (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_forward_rules),
                    1, 0, 0, 0, '::/0', NULL,
                    '::/0', NULL,
                    'icmpv6', ${icmp_type}, ${icmp_code},
                    'ACCEPT', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM filter_forward_rules
                        WHERE iface_in = 'ANY'
                            AND iface_out = 'ANY'
                            AND protocol_name = 'icmpv6'
                            AND protocol_type = ${icmp_type}
                            AND protocol_code = ${icmp_code}
                            AND action = 'ACCEPT'
                            AND enabled = 1
                );"
}

# Record and apply one ICMPv6 INPUT rule.
allow_icmpv6_input_rule() {
    local src_addr="$1"
    local icmp_type="$2"
    local icmp_code="$3"

    record_icmpv6_input_rule "$src_addr" "$icmp_type" "$icmp_code"
    apply_icmpv6_input_rule "$src_addr" "$icmp_type" "$icmp_code"
}

# Record and apply one ICMPv6 FORWARD rule.
allow_icmpv6_forward_rule() {
    local icmp_type="$1"
    local icmp_code="$2"

    record_icmpv6_forward_rule "$icmp_type" "$icmp_code"
    apply_icmpv6_forward_rule "$icmp_type" "$icmp_code"
}

# Register and apply ICMPv6 rules required for IPv6 to operate correctly.
allow_required_icmpv6() {
    log "Registering and applying required ICMPv6 rules."

    # Destination Unreachable, Packet Too Big, Time Exceeded, Parameter Problem.
    for rule in 1/0 1/1 1/2 1/3 1/4 1/5 1/6 1/7 2/0 3/0 3/1 4/0 4/1 4/2; do
        allow_icmpv6_input_rule "::/0" "${rule%/*}" "${rule#*/}"
        allow_icmpv6_forward_rule "${rule%/*}" "${rule#*/}"
    done

    # Router Solicitation, Router Advertisement, Neighbor Solicitation, Neighbor Advertisement.
    for rule in 133/0 134/0 135/0 136/0; do
        allow_icmpv6_input_rule "fe80::/10" "${rule%/*}" "${rule#*/}"
    done
}

# Record one filter chain policy in the selected database.
record_filter_policy() {
    local family="$1"
    local chain_name="$2"
    local policy="$3"
    local db_path

    db_path="$(filter_rules_db "$family")"

    sqlite_exec "$db_path" "
        INSERT INTO filter_chain_policies (
            chain_name,
            policy,
            created_at,
            updated_at
        ) VALUES (
            $(sql_quote "$chain_name"),
            $(sql_quote "$policy"),
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(chain_name) DO UPDATE SET
            policy = excluded.policy,
            updated_at = CURRENT_TIMESTAMP;
    "
}

# Record the default INPUT and FORWARD policies in IPv4 and IPv6 databases.
record_default_filter_policies() {
    record_filter_policy ipv4 INPUT DROP
    record_filter_policy ipv4 FORWARD DROP

    record_filter_policy ipv6 INPUT DROP
    record_filter_policy ipv6 FORWARD DROP
}

# Set restrictive default policies for IPv4 and IPv6 filter chains.
set_default_filter_policies() {
    log "Setting INPUT and FORWARD default policies to DROP."

    iptables -t filter -P INPUT DROP
    iptables -t filter -P FORWARD DROP
    
    ip6tables -t filter -P INPUT DROP
    ip6tables -t filter -P FORWARD DROP
}

# Register and apply LAN INPUT rules from ALLOW_LAN_TCP_PORTS 
# and ALLOW_LAN_UDP_PORTS
allow_lan_services() {
    local lan_iface="$1"
    local port

    log "Registering and applying LAN INPUT rules on ${lan_iface}."

    for port in "${ALLOW_LAN_TCP_PORTS[@]}"; do
        record_lan_input_rule ipv4 tcp "$lan_iface" "$port"
        record_lan_input_rule ipv6 tcp "$lan_iface" "$port"

        apply_lan_input_rule iptables tcp "$lan_iface" "$port"
        apply_lan_input_rule ip6tables tcp "$lan_iface" "$port"
    done

    for port in "${ALLOW_LAN_UDP_PORTS[@]}"; do
        record_lan_input_rule ipv4 udp "$lan_iface" "$port"
        record_lan_input_rule ipv6 udp "$lan_iface" "$port"

        apply_lan_input_rule iptables udp "$lan_iface" "$port"
        apply_lan_input_rule ip6tables udp "$lan_iface" "$port"
    done
}

main() {
    [[ -n "${LAN_IFACE:-}" ]] || fatal "LAN_IFACE is not set."

    allow_lan_services "$LAN_IFACE"
    record_conntrack_base_rules
    apply_conntrack_base_rules
    allow_required_icmpv6
    record_default_filter_policies
    set_default_filter_policies
}

main "$@"
