#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=globals.sh
. "$ROOT_DIR/bin/scripts/globals.sh"

# shellcheck source=log.sh
declare -F fatal >/dev/null 2>&1 || . "$ROOT_DIR/bin/scripts/log.sh"

ARMFW_USER="armfw"
ARMFW_GROUP="armfw"

# Create the ArmFirewall operating system group when missing.
ensure_armfw_group() {
    if getent group "$ARMFW_GROUP" >/dev/null 2>&1; then
        log "Operating system group already exists: ${ARMFW_GROUP}."
        return 0
    fi

    if groupadd --system "$ARMFW_GROUP" 2>/dev/null; then
        log "Created operating system group: ${ARMFW_GROUP}."
        return 0
    fi

    groupadd "$ARMFW_GROUP" || fatal "Could not create operating system group: ${ARMFW_GROUP}."
    
    log "Created operating system group: ${ARMFW_GROUP}."
}

# Create the ArmFirewall operating system user when missing.
ensure_armfw_user() {
    if id -u "$ARMFW_USER" >/dev/null 2>&1; then
        log "Operating system user already exists: ${ARMFW_USER}."
        return 0
    fi

    useradd \
        --system \
        --gid "$ARMFW_GROUP" \
        --home-dir "$ROOT_DIR" \
        --no-create-home \
        --shell /sbin/nologin \
        --comment "ArmFirewall service user" \
        "$ARMFW_USER" 2>/dev/null || \
    useradd \
        --gid "$ARMFW_GROUP" \
        --home-dir "$ROOT_DIR" \
        --no-create-home \
        --shell /usr/sbin/nologin \
        --comment "ArmFirewall service user" \
        "$ARMFW_USER" || \
    fatal "Could not create operating system user: ${ARMFW_USER}."

    log "Created operating system user: ${ARMFW_USER}."
}

# Prepare writable runtime directories for supervisord-managed processes.
prepare_runtime_permissions() {
    mkdir -p "$CONF_DIR" "$DB_DIR" "$ROOT_DIR/logs" "$ROOT_DIR/rrd" "$ROOT_DIR/rrd/img"

    chown -R "${ARMFW_USER}:${ARMFW_GROUP}" \
        "$CONF_DIR" \
        "$DB_DIR" \
        "$ROOT_DIR/logs" \
        "$ROOT_DIR/rrd"

    chmod 0750 "$CONF_DIR" "$DB_DIR" "$ROOT_DIR/logs" "$ROOT_DIR/rrd"
    chmod 0750 "$ROOT_DIR/rrd/img"

    if [[ -e "$CONF_DIR/armfirewall.key" ]]; then
        chown "${ARMFW_USER}:${ARMFW_GROUP}" "$CONF_DIR/armfirewall.key"
        chmod 0400 "$CONF_DIR/armfirewall.key"
    fi

    if [[ -e "$CONF_DIR/armfirewall.crt" ]]; then
        chown "${ARMFW_USER}:${ARMFW_GROUP}" "$CONF_DIR/armfirewall.crt"
        chmod 0400 "$CONF_DIR/armfirewall.crt"
    fi

    log "Prepared ArmFirewall runtime permissions for ${ARMFW_USER}:${ARMFW_GROUP}."
}

# Create the ArmFirewall operating system identity and runtime permissions.
main() {
    ensure_armfw_group
    ensure_armfw_user
    prepare_runtime_permissions
}

main "$@"
