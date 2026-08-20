#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=scripts/common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

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

# Return the NAT rules database path for the selected IP family.
nat_rules_db() {
    local family="$1"

    case "$family" in
        ipv4)
            printf '%s\n' "$IPV4_NAT_RULES_DB"
            ;;

        ipv6)
            printf '%s\n' "$IPV6_NAT_RULES_DB"
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

# Record one protected loopback rule in the selected filter rules database.
record_loopback_rule() {
    local family="$1"
    local chain_name="$2"
    local table_name iface_column
    local db_path
    local any_addr

    db_path="$(filter_rules_db "$family")"
    any_addr="$(filter_any_addr "$family")"

    case "$chain_name" in
        INPUT)
            table_name="filter_input_rules"
            iface_column="iface_in"
            ;;
        OUTPUT)
            table_name="filter_output_rules"
            iface_column="iface_out"
            ;;
        *)
            fatal "Unsupported loopback filter chain: ${chain_name}."
            ;;
    esac

    sqlite_exec "$db_path" "
        INSERT INTO ${table_name} (
            ${iface_column}, rule_order, ct_new, ct_established, ct_related,
            ct_invalid, src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code, action,
            protected, enabled, created_at, updated_at
        )
        SELECT
            'lo', 0, 0, 0, 0, 0,
            $(sql_quote "$any_addr"), NULL, $(sql_quote "$any_addr"), NULL,
            'all', NULL, NULL, 'ACCEPT',
            1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1
            FROM ${table_name}
            WHERE ${iface_column} = 'lo'
              AND protocol_name = 'all'
              AND action = 'ACCEPT'
              AND protected = 1
        );
    "
}

# Apply protected loopback INPUT and OUTPUT rules for IPv4 and IPv6.
apply_loopback_rules() {
    local binary

    log "Applying protected loopback rules for IPv4 and IPv6."

    for binary in iptables ip6tables; do
        "$binary" -t filter -C INPUT -i lo -j ACCEPT 2>/dev/null || \
        "$binary" -t filter -I INPUT 1 -i lo -j ACCEPT

        "$binary" -t filter -C OUTPUT -o lo -j ACCEPT 2>/dev/null || \
        "$binary" -t filter -I OUTPUT 1 -o lo -j ACCEPT
    done
}

# Persist protected loopback INPUT and OUTPUT rules for IPv4 and IPv6.
record_loopback_rules() {
    local family

    for family in ipv4 ipv6; do
        record_loopback_rule "$family" INPUT
        record_loopback_rule "$family" OUTPUT
    done
}

# Record one system-managed, editable DNS redirect to the local DNS service.
record_dns_redirect_rule() {
    local family="$1"
    local protocol="$2"
    local iface="$3"
    local db_path
    local any_addr

    db_path="$(nat_rules_db "$family")"
    any_addr="$(filter_any_addr "$family")"

    sqlite_exec "$db_path" "
        INSERT INTO nat_prerouting_rules (
            iface_in, rule_order, src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code,
            nat_action, to_addr, to_port,
            protected, rule_source, enabled, created_at, updated_at
        )
        SELECT
            $(sql_quote "$iface"), 0,
            $(sql_quote "$any_addr"), NULL, $(sql_quote "$any_addr"), 53,
            $(sql_quote "$protocol"), NULL, NULL,
            'REDIRECT', NULL, 53,
            0, 'system', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1
            FROM nat_prerouting_rules
            WHERE iface_in = $(sql_quote "$iface")
              AND protocol_name = $(sql_quote "$protocol")
              AND dst_port = 53
              AND nat_action = 'REDIRECT'
              AND to_port = 53
        );
    "
}

# Record one protected LAN block for DNS-over-TLS.
record_dns_over_tls_block_rule() {
    local family="$1"
    local iface="$2"
    local db_path
    local any_addr

    db_path="$(filter_rules_db "$family")"
    any_addr="$(filter_any_addr "$family")"

    sqlite_exec "$db_path" "
        INSERT INTO filter_forward_rules (
            iface_in, iface_out, rule_order, ct_new, ct_established, ct_related,
            ct_invalid, src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code, action,
            protected, enabled, created_at, updated_at
        )
        SELECT
            $(sql_quote "$iface"), 'ANY', 0, 0, 0, 0, 0,
            $(sql_quote "$any_addr"), 0, $(sql_quote "$any_addr"), 853,
            'tcp', NULL, NULL, 'REJECT',
            1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1
            FROM filter_forward_rules
            WHERE iface_in = $(sql_quote "$iface")
              AND protocol_name = 'tcp'
              AND dst_port = 853
              AND action = 'REJECT'
              AND protected = 1
        );
    "
}

# Apply one DNS redirect to the local DNS service.
apply_dns_redirect_rule() {
    local binary="$1"
    local protocol="$2"
    local iface="$3"

    "$binary" -t nat -C PREROUTING -i "$iface" -p "$protocol" --dport 53 -j REDIRECT --to-ports 53 2>/dev/null || \
    "$binary" -t nat -I PREROUTING 1 -i "$iface" -p "$protocol" --dport 53 -j REDIRECT --to-ports 53
}

# Apply one DNS-over-TLS block for LAN clients.
apply_dns_over_tls_block_rule() {
    local binary="$1"
    local iface="$2"

    "$binary" -t filter -C FORWARD -i "$iface" -p tcp --dport 853 -j REJECT 2>/dev/null || \
    "$binary" -t filter -I FORWARD 1 -i "$iface" -p tcp --dport 853 -j REJECT
}

# Persist and apply DNS enforcement rules for LAN clients.
enforce_lan_dns() {
    local lan_iface="$1"
    local family binary protocol

    log "Enforcing protected DNS redirection and DNS-over-TLS blocking on ${lan_iface}."

    for family in ipv4 ipv6; do
        record_dns_redirect_rule "$family" tcp "$lan_iface"
        record_dns_redirect_rule "$family" udp "$lan_iface"
        record_dns_over_tls_block_rule "$family" "$lan_iface"
    done

    for binary in iptables ip6tables; do
        for protocol in tcp udp; do
            apply_dns_redirect_rule "$binary" "$protocol" "$lan_iface"
        done
        apply_dns_over_tls_block_rule "$binary" "$lan_iface"
    done
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
                    0, 0, 0, 0, $(sql_quote "$src_addr"), NULL,
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
                );

                UPDATE filter_input_rules
                SET ct_new = 0,
                    ct_established = 0,
                    ct_related = 0,
                    ct_invalid = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE iface_in = 'ANY'
                    AND src_addr = $(sql_quote "$src_addr")
                    AND protocol_name = 'icmpv6'
                    AND protocol_type = ${icmp_type}
                    AND protocol_code = ${icmp_code}
                    AND action = 'ACCEPT';"
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

    # Router Solicitation and Router Advertisement are link-local by definition.
    for rule in 133/0 134/0; do
        allow_icmpv6_input_rule "fe80::/10" "${rule%/*}" "${rule#*/}"
    done

    # Neighbor Discovery messages can use the neighbor global IPv6 address.
    for rule in 135/0 136/0; do
        allow_icmpv6_input_rule "::/0" "${rule%/*}" "${rule#*/}"
    done
}

# Record and apply DHCP client reply rules required on the WAN interface.
record_wan_dhcp_input_rule() {
    local family="$1"
    local protocol="$2"
    local iface="$3"
    local source_port="$4"
    local destination_port="$5"
    local db_path any_addr

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
            0, 0, 0, 0, $(sql_quote "$any_addr"), ${source_port},
            $(sql_quote "$any_addr"), ${destination_port},
            $(sql_quote "$protocol"), NULL, NULL, 'ACCEPT',
            1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM filter_input_rules
            WHERE iface_in = $(sql_quote "$iface")
              AND src_port = ${source_port}
              AND dst_port = ${destination_port}
              AND protocol_name = $(sql_quote "$protocol")
              AND action = 'ACCEPT'
              AND protected = 1
        );

        UPDATE filter_input_rules
        SET ct_new = 0,
            ct_established = 0,
            ct_related = 0,
            ct_invalid = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE iface_in = $(sql_quote "$iface")
          AND src_port = ${source_port}
          AND dst_port = ${destination_port}
          AND protocol_name = $(sql_quote "$protocol")
          AND action = 'ACCEPT'
          AND protected = 1;"
}

apply_wan_dhcp_input_rule() {
    local binary="$1"
    local protocol="$2"
    local iface="$3"
    local source_port="$4"
    local destination_port="$5"

    "$binary" -t filter -C INPUT -i "$iface" -p "$protocol" --sport "$source_port" --dport "$destination_port" -j ACCEPT 2>/dev/null || \
    "$binary" -t filter -I INPUT 1 -i "$iface" -p "$protocol" --sport "$source_port" --dport "$destination_port" -j ACCEPT
}

allow_wan_dhcp_client() {
    local wan_iface="$1"

    [[ -n "$wan_iface" ]] || return 0
    log "Allowing DHCP client replies on WAN interface ${wan_iface}."
    record_wan_dhcp_input_rule ipv4 udp "$wan_iface" 67 68
    apply_wan_dhcp_input_rule iptables udp "$wan_iface" 67 68
    record_wan_dhcp_input_rule ipv6 udp "$wan_iface" 547 546
    apply_wan_dhcp_input_rule ip6tables udp "$wan_iface" 547 546
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

# Return a JSON array with enabled rule ids for one filter table.
filter_rule_ids_json() {
    local db_path="$1"
    local table_name="$2"

    sqlite_query "$db_path" "
        SELECT '[' || COALESCE(group_concat(id), '') || ']'
        FROM (
            SELECT id
            FROM ${table_name}
            WHERE enabled = 1 AND COALESCE(pending_delete, 0) = 0
            ORDER BY rule_order, id
        );
    "
}

# Return the persisted policy for one filter chain.
filter_policy_for_chain() {
    local db_path="$1"
    local chain_name="$2"
    local fallback="$3"
    local policy

    policy="$(sqlite_query "$db_path" "SELECT policy FROM filter_chain_policies WHERE chain_name=$(sql_quote "$chain_name") LIMIT 1;")"
    [[ -n "$policy" ]] && printf '%s\n' "$policy" || printf '%s\n' "$fallback"
}

# Return a generated request UID.
new_request_uid() {
    if [[ -r /proc/sys/kernel/random/uuid ]]; then
        cat /proc/sys/kernel/random/uuid
    elif command -v uuidgen >/dev/null 2>&1; then
        uuidgen
    else
        printf 'install-%s-%s\n' "$(date +%s)" "$RANDOM"
    fi
}

# Record one install-time firewall apply work request when the queue exists.
record_install_filter_apply_work_request() {
    local family="$1"
    local chain_name="$2"
    local table_name="$3"
    local policy_fallback="$4"
    local db_path family_upper category_name rule_ids policy request_uid payload

    db_path="$(filter_rules_db "$family")"
    family_upper="${family^^}"
    category_name="FIREWALL_RULES.${family_upper}.${table_name}"

    [[ -f "$WORK_REQUEST_DB" ]] || return 0
    sqlite_table_exists "$WORK_REQUEST_DB" "work_requests" || return 0
    sqlite_table_exists "$WORK_REQUEST_DB" "work_request_events" || return 0
    sqlite_table_exists "$db_path" "$table_name" || return 0
    ensure_pending_delete_column "$db_path" "$table_name"

    rule_ids="$(filter_rule_ids_json "$db_path" "$table_name")"
    policy="$(filter_policy_for_chain "$db_path" "$chain_name" "$policy_fallback")"
    request_uid="$(new_request_uid)"
    payload="{\"family\":\"${family_upper}\",\"chain\":\"${chain_name}\",\"table\":\"${table_name}\",\"policy\":\"${policy}\",\"rule_ids\":${rule_ids:-[]},\"delete_rule_ids\":[]}"

    sqlite_exec "$WORK_REQUEST_DB" "
        INSERT INTO work_requests (
            request_uid, source, category_name, action_name,
            target_rule_id, priority, status, payload_json
        ) VALUES (
            $(sql_quote "$request_uid"),
            'system',
            $(sql_quote "$category_name"),
            'apply',
            NULL,
            90,
            'queue',
            $(sql_quote "$payload")
        );

        INSERT INTO work_request_events (work_request_id, event_type, message)
        VALUES (
            last_insert_rowid(),
            'queue',
            $(sql_quote "Queued install-time apply for ${category_name}.")
        );
    "
}

# Record install-time apply requests for the default filter chains.
record_install_filter_apply_work_requests() {
    record_install_filter_apply_work_request ipv4 INPUT filter_input_rules DROP
    record_install_filter_apply_work_request ipv4 FORWARD filter_forward_rules DROP
    record_install_filter_apply_work_request ipv4 OUTPUT filter_output_rules ACCEPT
    record_install_filter_apply_work_request ipv6 INPUT filter_input_rules DROP
    record_install_filter_apply_work_request ipv6 FORWARD filter_forward_rules DROP
    record_install_filter_apply_work_request ipv6 OUTPUT filter_output_rules ACCEPT
}

# Record the already applied DNS redirect rules in the installation history.
record_install_dns_nat_apply_work_requests() {
    record_install_apply_work_request "NAT_RULES.IPV4.nat_prerouting_rules" "fwrules.sh"
    record_install_apply_work_request "NAT_RULES.IPV6.nat_prerouting_rules" "fwrules.sh"
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
    allow_wan_dhcp_client "${WAN_IFACE:-}"
    record_conntrack_base_rules
    apply_conntrack_base_rules
    record_loopback_rules
    apply_loopback_rules
    enforce_lan_dns "$LAN_IFACE"
    allow_required_icmpv6
    record_default_filter_policies
    set_default_filter_policies
    record_install_filter_apply_work_requests
    record_install_dns_nat_apply_work_requests
}

main "$@"
