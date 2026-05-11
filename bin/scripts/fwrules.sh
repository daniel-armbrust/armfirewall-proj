#!/usr/bin/env bash

IPV4_FIREWALL_RULES_DB="${IPV4_FIREWALL_RULES_DB:-$ROOT_DIR/db/ipv4-firewall-rules.db}"
IPV6_FIREWALL_RULES_DB="${IPV6_FIREWALL_RULES_DB:-$ROOT_DIR/db/ipv6-firewall-rules.db}"
LAN_PORTS_TCP=(22 8000 53)
LAN_PORTS_UDP=(67 53)

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

# Return whether a numeric firewall field has a usable value.
has_numeric_value() {
    local value="$1"

    [[ -n "$value" && "$value" != "0" ]]
}

# Return the iptables protocol name for one stored protocol.
iptables_protocol_name() {
    local family="$1"
    local protocol="$2"

    if [[ "$protocol" == "all" ]]; then
        printf '\n'
        return 0
    fi

    if [[ "$family" == "ipv6" && "$protocol" == "icmpv6" ]]; then
        printf 'ipv6-icmp\n'
        return 0
    fi

    printf '%s\n' "$protocol"
}

# Return the filter rule database path for a firewall family.
filter_rules_db_for_family() {
    local family="$1"

    case "$family" in
        ipv4)
            printf '%s\n' "$IPV4_FIREWALL_RULES_DB"
            ;;
        ipv6)
            printf '%s\n' "$IPV6_FIREWALL_RULES_DB"
            ;;
        *)
            fatal "Unsupported firewall rule family: ${family}."
            ;;
    esac
}

# Return the wildcard address for a firewall family.
wildcard_addr_for_family() {
    local family="$1"

    case "$family" in
        ipv4)
            printf '0.0.0.0/0\n'
            ;;
        ipv6)
            printf '::/0\n'
            ;;
        *)
            fatal "Unsupported firewall rule family: ${family}."
            ;;
    esac
}

# Store one LAN INPUT allow rule in the matching firewall rule database.
record_lan_input_rule() {
    local family="$1"
    local protocol="$2"
    local iface="$3"
    local port="$4"
    local protected="$5"
    local db_path
    local src_addr
    local dst_addr
    local sql

    db_path="$(filter_rules_db_for_family "$family")"
    src_addr="$(wildcard_addr_for_family "$family")"
    dst_addr="$(wildcard_addr_for_family "$family")"

    sql="
        PRAGMA foreign_keys = ON;
        INSERT INTO filter_input_rules (
            iface_in, rule_order,
            ct_new, ct_established, ct_related, ct_invalid,
            src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code,
            action, protected, enabled,
            created_at, updated_at
        )
        SELECT
            $(sql_quote "$iface"),
            (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_input_rules),
            0, 0, 0, 0,
            $(sql_quote "$src_addr"), 0, $(sql_quote "$dst_addr"), ${port},
            $(sql_quote "$protocol"), NULL, NULL,
            'ACCEPT', ${protected}, 1,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1
            FROM filter_input_rules
            WHERE iface_in = $(sql_quote "$iface")
              AND protocol_name = $(sql_quote "$protocol")
              AND src_addr = $(sql_quote "$src_addr")
              AND src_port = 0
              AND dst_addr = $(sql_quote "$dst_addr")
              AND dst_port = ${port}
              AND action = 'ACCEPT'
        );

        UPDATE filter_input_rules
        SET protected = 1,
            enabled = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE ${protected} = 1
          AND iface_in = $(sql_quote "$iface")
          AND protocol_name = $(sql_quote "$protocol")
          AND src_addr = $(sql_quote "$src_addr")
          AND src_port = 0
          AND dst_addr = $(sql_quote "$dst_addr")
          AND dst_port = ${port}
          AND action = 'ACCEPT';
    "

    sqlite_exec "$db_path" "$sql"
}

# Build a comma-separated conntrack state list from stored flags.
conntrack_states() {
    local ct_new="$1"
    local ct_established="$2"
    local ct_related="$3"
    local ct_invalid="$4"
    local states=()

    [[ "$ct_new" == "1" ]] && states+=("NEW")
    [[ "$ct_established" == "1" ]] && states+=("ESTABLISHED")
    [[ "$ct_related" == "1" ]] && states+=("RELATED")
    [[ "$ct_invalid" == "1" ]] && states+=("INVALID")

    local IFS=,
    printf '%s\n' "${states[*]}"
}

# Apply one persisted filter rule to iptables or ip6tables when it is missing.
apply_persisted_filter_rule() {
    local family="$1"
    local binary="$2"
    local chain="$3"
    local rule_id="$4"
    local iface_in="$5"
    local iface_out="$6"
    local ct_new="$7"
    local ct_established="$8"
    local ct_related="$9"
    local ct_invalid="${10}"
    local src_addr="${11}"
    local src_port="${12}"
    local dst_addr="${13}"
    local dst_port="${14}"
    local protocol_name="${15}"
    local protocol_type="${16}"
    local protocol_code="${17}"
    local action="${18}"
    local protocol
    local states
    local icmp_type
    local -a match_args=()

    case "$chain" in
        INPUT)
            [[ -n "$iface_in" ]] && match_args+=("-i" "$iface_in")
            ;;
        FORWARD)
            [[ -n "$iface_in" ]] && match_args+=("-i" "$iface_in")
            [[ -n "$iface_out" ]] && match_args+=("-o" "$iface_out")
            ;;
        OUTPUT)
            [[ -n "$iface_out" ]] && match_args+=("-o" "$iface_out")
            ;;
        *)
            fatal "Unsupported filter chain in SQLite rule ${rule_id}: ${chain}."
            ;;
    esac

    states="$(conntrack_states "$ct_new" "$ct_established" "$ct_related" "$ct_invalid")"
    [[ -n "$states" ]] && match_args+=("-m" "conntrack" "--ctstate" "$states")

    [[ -n "$src_addr" ]] && match_args+=("-s" "$src_addr")
    [[ -n "$dst_addr" ]] && match_args+=("-d" "$dst_addr")

    protocol="$(iptables_protocol_name "$family" "$protocol_name")"
    [[ -n "$protocol" ]] && match_args+=("-p" "$protocol")

    if [[ "$protocol_name" == "tcp" || "$protocol_name" == "udp" ]]; then
        has_numeric_value "$src_port" && match_args+=("--sport" "$src_port")
        has_numeric_value "$dst_port" && match_args+=("--dport" "$dst_port")
    elif [[ "$protocol_name" == "icmp" || "$protocol_name" == "icmpv6" ]]; then
        if has_numeric_value "$protocol_type"; then
            icmp_type="$protocol_type"
            has_numeric_value "$protocol_code" && icmp_type="${icmp_type}/${protocol_code}"

            if [[ "$family" == "ipv6" ]]; then
                match_args+=("--icmpv6-type" "$icmp_type")
            else
                match_args+=("--icmp-type" "$icmp_type")
            fi
        fi
    fi

    if ! "$binary" -t filter -C "$chain" "${match_args[@]}" -j "$action" 2>/dev/null; then
        "$binary" -t filter -A "$chain" "${match_args[@]}" -j "$action"
    fi
}

# Apply enabled filter rules persisted in one SQLite firewall database.
apply_persisted_filter_db() {
    local family="$1"
    local binary="$2"
    local db_path="$3"
    local query
    local chain_sort chain rule_id rule_order iface_in iface_out
    local ct_new ct_established ct_related ct_invalid
    local src_addr src_port dst_addr dst_port
    local protocol_name protocol_type protocol_code action
    local rows

    [[ -f "$db_path" ]] || fatal "SQLite database was not found: ${db_path}."

    query="
        SELECT 1, 'INPUT', id, rule_order, iface_in, '',
               ct_new, ct_established, ct_related, ct_invalid,
               src_addr, COALESCE(src_port, ''), dst_addr, COALESCE(dst_port, ''),
               protocol_name, COALESCE(protocol_type, ''), COALESCE(protocol_code, ''), action
        FROM filter_input_rules
        WHERE enabled = 1
        UNION ALL
        SELECT 2, 'FORWARD', id, rule_order, iface_in, iface_out,
               ct_new, ct_established, ct_related, ct_invalid,
               src_addr, COALESCE(src_port, ''), dst_addr, COALESCE(dst_port, ''),
               protocol_name, COALESCE(protocol_type, ''), COALESCE(protocol_code, ''), action
        FROM filter_forward_rules
        WHERE enabled = 1
        UNION ALL
        SELECT 3, 'OUTPUT', id, rule_order, '', iface_out,
               ct_new, ct_established, ct_related, ct_invalid,
               src_addr, COALESCE(src_port, ''), dst_addr, COALESCE(dst_port, ''),
               protocol_name, COALESCE(protocol_type, ''), COALESCE(protocol_code, ''), action
        FROM filter_output_rules
        WHERE enabled = 1
        ORDER BY 1, 4, 3;
    "

    rows="$(sqlite3 -noheader -separator '|' "$db_path" "$query")" || \
        fatal "Could not read persisted filter rules from ${db_path}."
    [[ -n "$rows" ]] || return 0

    while IFS='|' read -r chain_sort chain rule_id rule_order iface_in iface_out \
        ct_new ct_established ct_related ct_invalid src_addr src_port dst_addr dst_port \
        protocol_name protocol_type protocol_code action; do
        [[ -n "$rule_id" ]] || continue
        apply_persisted_filter_rule \
            "$family" "$binary" "$chain" "$rule_id" "$iface_in" "$iface_out" \
            "$ct_new" "$ct_established" "$ct_related" "$ct_invalid" \
            "$src_addr" "$src_port" "$dst_addr" "$dst_port" \
            "$protocol_name" "$protocol_type" "$protocol_code" "$action"
    done <<< "$rows"
}

# Apply enabled IPv4 and IPv6 filter rules persisted by the GUI.
apply_persisted_filter_rules() {
    log "Applying enabled persisted filter rules from SQLite."
    apply_persisted_filter_db ipv4 iptables "$IPV4_FIREWALL_RULES_DB"
    apply_persisted_filter_db ipv6 ip6tables "$IPV6_FIREWALL_RULES_DB"
}

# Clear existing firewall rules and prepare tables for a clean rebuild.
initialize_firewall_rules() {
    disable_os_firewall_services

    log "Clearing existing iptables and ip6tables rules before rebuilding ArmFirewall rules."

    iptables -t filter -P INPUT ACCEPT
    iptables -t filter -P FORWARD ACCEPT
    iptables -t filter -P OUTPUT ACCEPT
    iptables -t filter -F
    iptables -t filter -X
    iptables -t filter -Z

    iptables -t nat -F
    iptables -t nat -X
    iptables -t nat -Z

    ip6tables -t filter -P INPUT ACCEPT
    ip6tables -t filter -P FORWARD ACCEPT
    ip6tables -t filter -P OUTPUT ACCEPT
    ip6tables -t filter -F
    ip6tables -t filter -X
    ip6tables -t filter -Z
}

# Set restrictive default policies after required allow rules exist.
set_default_policies() {
    [[ "${ARMFIREWALL_BOOTSTRAP:-0}" == "1" ]] || \
        fatal "set_default_policies can only run during ArmFirewall bootstrap."

    log "Setting INPUT and FORWARD policies to DROP."

    iptables -t filter -P INPUT DROP
    iptables -t filter -P FORWARD DROP

    ip6tables -t filter -P INPUT DROP
    ip6tables -t filter -P FORWARD DROP
}

# Add a filtered allow rule only when it is not already present.
allow_rule_if_missing() {
    local binary="$1"
    local chain="$2"
    local protocol="$3"
    local iface="$4"
    local port="$5"

    if ! "$binary" -t filter -C "$chain" -i "$iface" -p "$protocol" --dport "$port" -j ACCEPT 2>/dev/null; then
        "$binary" -t filter -A "$chain" -i "$iface" -p "$protocol" --dport "$port" -j ACCEPT
    fi
}

# Add common loopback and established-connection allow rules.
allow_base_rules() {
    local binary="$1"

    if ! "$binary" -t filter -C INPUT -i lo -j ACCEPT 2>/dev/null; then
        "$binary" -t filter -I INPUT 1 -i lo -j ACCEPT
    fi

    if ! "$binary" -t filter -C INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
        "$binary" -t filter -I INPUT 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    fi

    if ! "$binary" -t filter -C FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
        "$binary" -t filter -I FORWARD 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    fi
}

# Allow required service ports only on the selected LAN interface.
allow_lan_services() {
    local lan_iface="$1"
    local port
    local protected

    if [[ "$lan_iface" == *[[:space:]]* ]]; then
        fatal "Only one LAN interface is allowed. Current value: ${lan_iface}."
    fi

    log "Allowing LAN access only on ${lan_iface}."

    allow_base_rules iptables
    allow_base_rules ip6tables

    for port in "${LAN_PORTS_TCP[@]}"; do
        allow_rule_if_missing iptables INPUT tcp "$lan_iface" "$port"
        allow_rule_if_missing ip6tables INPUT tcp "$lan_iface" "$port"
        protected=1
        record_lan_input_rule ipv4 tcp "$lan_iface" "$port" "$protected"
        record_lan_input_rule ipv6 tcp "$lan_iface" "$port" "$protected"
    done

    for port in "${LAN_PORTS_UDP[@]}"; do
        allow_rule_if_missing iptables INPUT udp "$lan_iface" "$port"
        allow_rule_if_missing ip6tables INPUT udp "$lan_iface" "$port"
        record_lan_input_rule ipv4 udp "$lan_iface" "$port" 1
        record_lan_input_rule ipv6 udp "$lan_iface" "$port" 1
    done
}

# Allow forwarding from LAN to WAN and return traffic back to LAN.
allow_forward_to_wan() {
    local lan_iface="$1"
    local wan_iface="$2"

    log "Allowing forwarded traffic from LAN ${lan_iface} to WAN ${wan_iface}."

    if ! iptables -t filter -C FORWARD -i "$lan_iface" -o "$wan_iface" -j ACCEPT 2>/dev/null; then
        iptables -t filter -A FORWARD -i "$lan_iface" -o "$wan_iface" -j ACCEPT
    fi

    if ! iptables -t filter -C FORWARD -i "$wan_iface" -o "$lan_iface" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; then
        iptables -t filter -A FORWARD -i "$wan_iface" -o "$lan_iface" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    fi
}

# Enable IPv4 forwarding and NAT masquerading through the WAN interface.
configure_masquerade() {
    local wan_iface="$1"

    if [[ "$wan_iface" == *[[:space:]]* ]]; then
        fatal "Only one WAN interface is allowed. Current value: ${wan_iface}."
    fi

    log "Enabling IPv4 forwarding for LAN to WAN traffic."
    sysctl -w net.ipv4.ip_forward=1 >/dev/null || fatal "Could not enable IPv4 forwarding."

    log "Ensuring IPv4 MASQUERADE through WAN interface ${wan_iface}."

    if ! iptables -t nat -C POSTROUTING -o "$wan_iface" -j MASQUERADE 2>/dev/null; then
        iptables -t nat -A POSTROUTING -o "$wan_iface" -j MASQUERADE
    fi
}
