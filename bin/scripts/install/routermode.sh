#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Validate the WAN interface when it was provided by install.sh.
validate_wan_iface() {
    [[ -n "${WAN_IFACE:-}" ]] || return 0
    [[ "$WAN_IFACE" != "lo" ]] || fatal "Loopback cannot be used as the WAN interface."
    ip link show dev "$WAN_IFACE" >/dev/null 2>&1 || fatal "WAN interface was not found: ${WAN_IFACE}."
}

# Persist the selected WAN interface in iface.db when provided.
persist_wan_iface_db() {
    local active
    local mtu
    local mac
    local iface_sql
    local mac_sql
    local description_sql

    [[ -n "${WAN_IFACE:-}" ]] || return 0
    [[ -f "$IFACE_DB" ]] || fatal "Interface database was not found: ${IFACE_DB}."

    if [[ "$WAN_IFACE" == "${LAN_IFACE:-}" ]]; then
        log "WAN interface is the same as LAN interface; keeping existing LAN record in ${IFACE_DB}: ${WAN_IFACE}."
        return 0
    fi

    active="$(net_iface_active_flag "$WAN_IFACE")"
    mtu="$(net_iface_mtu "$WAN_IFACE")"
    mac="$(net_iface_mac "$WAN_IFACE")"

    iface_sql="$(sql_quote "$WAN_IFACE")"
    mac_sql="$(sql_quote "$mac")"
    description_sql="$(sql_quote "WAN interface configured during ArmFirewall install: ${WAN_IFACE}")"

    sqlite_exec "$IFACE_DB" "
UPDATE ifaces
   SET role = 'UNKNOWN',
       protected = 0,
       collected_at = CURRENT_TIMESTAMP
 WHERE role = 'WAN'
   AND name <> ${iface_sql};

INSERT INTO ifaces (
    name,
    is_actived,
    description,
    mtu,
    mac_address,
    role,
    type,
    speed_mbps,
    duplex,
    protected,
    collected_at
) VALUES (
    ${iface_sql},
    ${active},
    ${description_sql},
    ${mtu},
    ${mac_sql},
    'WAN',
    'Ethernet',
    0,
    'unknown',
    0,
    CURRENT_TIMESTAMP
)
ON CONFLICT(name) DO UPDATE SET
    is_actived = excluded.is_actived,
    description = excluded.description,
    mtu = excluded.mtu,
    mac_address = excluded.mac_address,
    role = 'WAN',
    protected = 0,
    collected_at = CURRENT_TIMESTAMP;
"

    log "WAN interface saved to ${IFACE_DB}: ${WAN_IFACE}."
}

# Return whether router mode was requested by install.sh.
router_mode_enabled() {
    [[ "${ROUTER_MODE:-0}" == "1" ]]
}

# Enable IPv4 and IPv6 packet forwarding for router mode.
enable_packet_forward() {
    log "Enabling IPv4 and IPv6 packet forwarding."

    sysctl -w net.ipv4.ip_forward=1 >/dev/null || fatal "Could not enable IPv4 packet forwarding."
    sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null || fatal "Could not enable IPv6 packet forwarding."
    sysctl -w net.ipv6.conf.default.forwarding=1 >/dev/null || fatal "Could not enable default IPv6 packet forwarding."
}

# Record one forwarding kernel parameter in proc.db.
record_forward_proc_value() {
    local category="$1"
    local name="$2"
    local proc_path="$3"
    local description="$4"

    sqlite_exec "$PROC_DB" "
        INSERT INTO proc (
            category,
            name,
            proc_path,
            description,
            default_value,
            current_value,
            desired_value,
            protected,
            enabled,
            collected_at,
            updated_at
        ) VALUES (
            $(sql_quote "$category"),
            $(sql_quote "$name"),
            $(sql_quote "$proc_path"),
            $(sql_quote "$description"),
            '0',
            '1',
            '1',
            0,
            1,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(proc_path) DO UPDATE SET
            current_value = '1',
            desired_value = '1',
            enabled = 1,
            collected_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP;
    "
}

# Record router mode forwarding kernel parameters in proc.db.
record_forward_proc_values() {
    record_forward_proc_value \
        "IPv4" \
        "net.ipv4.ip_forward" \
        "/proc/sys/net/ipv4/ip_forward" \
        "Enables IPv4 packet forwarding between interfaces."

    record_forward_proc_value \
        "IPv6" \
        "net.ipv6.conf.all.forwarding" \
        "/proc/sys/net/ipv6/conf/all/forwarding" \
        "Enables IPv6 packet forwarding globally."

    record_forward_proc_value \
        "IPv6" \
        "net.ipv6.conf.default.forwarding" \
        "/proc/sys/net/ipv6/conf/default/forwarding" \
        "Controls IPv6 forwarding inherited by new interfaces."
}

# Apply NAT masquerade through the WAN interface.
apply_masquerade_rule() {
    log "Applying IPv4 MASQUERADE on WAN interface ${WAN_IFACE}."

    iptables -t nat -C POSTROUTING -o "$WAN_IFACE" -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -o "$WAN_IFACE" -j MASQUERADE
}

# Register the router mode MASQUERADE rule in SQLite.
record_masquerade_rule() {
    sqlite_exec "$IPV4_NAT_RULES_DB" "
        INSERT INTO nat_postrouting_rules (
            iface_out, rule_order,
            src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code,
            nat_action, to_addr, to_port,
            protected, enabled, created_at, updated_at
        )
            SELECT
                $(sql_quote "$WAN_IFACE"),
                (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM nat_postrouting_rules),
                '0.0.0.0/0', NULL, '0.0.0.0/0', NULL,
                'all', NULL, NULL,
                'MASQUERADE', NULL, NULL,
                0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM nat_postrouting_rules
                    WHERE iface_out = $(sql_quote "$WAN_IFACE")
                        AND protocol_name = 'all'
                        AND nat_action = 'MASQUERADE'
                        AND enabled = 1
            );"
}

# Apply the IPv4 FORWARD rule required for new LAN to WAN connections.
apply_ipv4_router_forward_rules() {
    log "Applying IPv4 router mode FORWARD rule from ${LAN_IFACE} to ${WAN_IFACE}."

    iptables -t filter -C FORWARD -i "$LAN_IFACE" -o "$WAN_IFACE" -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null || \
    iptables -t filter -A FORWARD -i "$LAN_IFACE" -o "$WAN_IFACE" -m conntrack --ctstate NEW -j ACCEPT
}

# Apply the IPv6 FORWARD rule required for new LAN to WAN connections.
apply_ipv6_router_forward_rules() {
    log "Applying IPv6 router mode FORWARD rule from ${LAN_IFACE} to ${WAN_IFACE}."

    ip6tables -t filter -C FORWARD -i "$LAN_IFACE" -o "$WAN_IFACE" -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null || \
    ip6tables -t filter -A FORWARD -i "$LAN_IFACE" -o "$WAN_IFACE" -m conntrack --ctstate NEW -j ACCEPT
}

# Register one router mode FORWARD rule in SQLite.
record_router_forward_rule() {
    local db_path="$1"
    local any_addr="$2"
    local iface_in="$3"
    local iface_out="$4"
    local ct_new="$5"
    local ct_established="$6"
    local ct_related="$7"

    sqlite_exec "$db_path" "
        INSERT INTO filter_forward_rules (
            iface_in, iface_out, rule_order,
            ct_new, ct_established, ct_related, ct_invalid,
            src_addr, src_port, dst_addr, dst_port,
            protocol_name, protocol_type, protocol_code,
            action, protected, enabled, created_at, updated_at
        )
            SELECT
                $(sql_quote "$iface_in"), $(sql_quote "$iface_out"),
                (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_forward_rules),
                ${ct_new}, ${ct_established}, ${ct_related}, 0,
                $(sql_quote "$any_addr"), NULL, $(sql_quote "$any_addr"), NULL,
                'all', NULL, NULL,
                'ACCEPT', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1 FROM filter_forward_rules
                    WHERE iface_in = $(sql_quote "$iface_in")
                        AND iface_out = $(sql_quote "$iface_out")
                        AND protocol_name = 'all'
                        AND ct_new = ${ct_new}
                        AND ct_established = ${ct_established}
                        AND ct_related = ${ct_related}
                        AND action = 'ACCEPT'
                        AND enabled = 1
            );"
}

# Register the router mode FORWARD rules in SQLite.
record_router_forward_rules() {
    record_router_forward_rule "$IPV4_FILTER_RULES_DB" "0.0.0.0/0" "$LAN_IFACE" "$WAN_IFACE" 1 0 0
    record_router_forward_rule "$IPV6_FILTER_RULES_DB" "::/0" "$LAN_IFACE" "$WAN_IFACE" 1 0 0
}

# Queue a full FORWARD chain reapply after router-mode rules are persisted.
#
# fwrules.sh queues its initial chain apply before routermode.sh inserts the
# LAN-to-WAN rules. Its payload therefore does not include those new rule IDs.
# This request is queued afterwards so the one-shot firewall executor flushes
# and rebuilds the chain with the complete persisted rule set.
queue_router_forward_apply() {
    local family="$1"
    local db_path="$2"
    local family_upper
    local category_name
    local rule_ids
    local policy
    local request_uid
    local payload

    family_upper="${family^^}"
    category_name="FIREWALL_RULES.${family_upper}.filter_forward_rules"
    rule_ids="$(sqlite_query "$db_path" "
        SELECT '[' || COALESCE(group_concat(id), '') || ']'
        FROM (
            SELECT id
            FROM filter_forward_rules
            WHERE enabled = 1 AND COALESCE(pending_delete, 0) = 0
            ORDER BY rule_order, id
        );")"
    policy="$(sqlite_query "$db_path" "SELECT policy FROM filter_chain_policies WHERE chain_name = 'FORWARD' LIMIT 1;")"
    policy="${policy:-DROP}"
    request_uid="$(cat /proc/sys/kernel/random/uuid)"
    payload="{\"family\":\"${family_upper}\",\"chain\":\"FORWARD\",\"table\":\"filter_forward_rules\",\"policy\":\"${policy}\",\"rule_ids\":${rule_ids:-[]},\"delete_rule_ids\":[]}"

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
            $(sql_quote "Queued router-mode FORWARD apply for ${family_upper}.")
        );
    "
}

# Queue the router-mode reapply requests after the initial direct system apply.
queue_router_apply_state() {
    queue_router_forward_apply ipv4 "$IPV4_FILTER_RULES_DB"
    queue_router_forward_apply ipv6 "$IPV6_FILTER_RULES_DB"
    record_install_apply_work_request "NAT_RULES.IPV4.nat_postrouting_rules" "routermode.sh"
}

# Apply IPv4 and IPv6 router mode FORWARD rules.
apply_router_forward_rules() {
    apply_ipv4_router_forward_rules
    apply_ipv6_router_forward_rules
}

# Configure router mode when explicitly requested.
configure_router_mode() {
    router_mode_enabled || return 0
    [[ -n "${WAN_IFACE:-}" ]] || fatal "--router-mode requires WAN_IFACE."

    enable_packet_forward
    record_forward_proc_values
    record_masquerade_rule
    apply_masquerade_rule
    record_router_forward_rules
    apply_router_forward_rules
    queue_router_apply_state
}

# Persist WAN interface and optionally enable router mode.
main() {
    validate_wan_iface
    persist_wan_iface_db
    configure_router_mode
}

main "$@"
