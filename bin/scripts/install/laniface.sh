#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Validate the selected LAN interface before persisting it.
validate_lan_iface() {
    [[ -n "${LAN_IFACE:-}" ]] || fatal "LAN_IFACE is not set."
    [[ "$LAN_IFACE" != "lo" ]] || fatal "Loopback cannot be used as the LAN interface."
    ip link show dev "$LAN_IFACE" >/dev/null 2>&1 || fatal "LAN interface was not found: ${LAN_IFACE}."
}

# Register the selected LAN interface in iface.db.
persist_lan_iface_db() {
    local active
    local mtu
    local mac
    local iface_sql
    local mac_sql
    local description_sql

    [[ -f "$IFACE_DB" ]] || fatal "Interface database was not found: ${IFACE_DB}."

    active="$(net_iface_active_flag "$LAN_IFACE")"
    mtu="$(net_iface_mtu "$LAN_IFACE")"
    mac="$(net_iface_mac "$LAN_IFACE")"

    iface_sql="$(sql_quote "$LAN_IFACE")"
    mac_sql="$(sql_quote "$mac")"
    description_sql="$(sql_quote "LAN interface configured during ArmFirewall install: ${LAN_IFACE}")"

    sqlite_exec "$IFACE_DB" "
UPDATE ifaces
   SET role = 'UNKNOWN',
       protected = 0,
       collected_at = CURRENT_TIMESTAMP
 WHERE role = 'LAN'
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
    'LAN',
    'Ethernet',
    0,
    'unknown',
    1,
    CURRENT_TIMESTAMP
)
ON CONFLICT(name) DO UPDATE SET
    is_actived = excluded.is_actived,
    description = excluded.description,
    mtu = excluded.mtu,
    mac_address = excluded.mac_address,
    role = 'LAN',
    protected = 1,
    collected_at = CURRENT_TIMESTAMP;
"

    log "LAN interface saved to ${IFACE_DB}: ${LAN_IFACE}."
}

main() {
    validate_lan_iface
    persist_lan_iface_db
}

main "$@"
