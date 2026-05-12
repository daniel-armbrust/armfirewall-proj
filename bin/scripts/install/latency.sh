#!/usr/bin/env bash

LATENCY_DB="${LATENCY_DB:-$ROOT_DIR/db/latency.db}"
LATENCY_DEFAULT_COUNT="${LATENCY_DEFAULT_COUNT:-3}"
LATENCY_DEFAULT_TIMEOUT="${LATENCY_DEFAULT_TIMEOUT:-3}"
LATENCY_DEFAULT_TARGETS=(8.8.8.8 registro.br)

# Return a SQL-safe quoted string.
latency_sql_quote() {
    local value="${1//\'/\'\'}"

    printf "'%s'" "$value"
}

# Verify that execddl.sh already created the latency database.
require_latency_db() {
    command -v sqlite3 >/dev/null 2>&1 || fatal "sqlite3 is required to store latency targets."
    [[ -f "$LATENCY_DB" ]] || fatal "Latency database was not found: ${LATENCY_DB}. Run bin/scripts/install/execddl.sh first."

    sqlite3 "$LATENCY_DB" "
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'latency_targets';
    " | grep -qx '1' || fatal "Latency database schema is incomplete: ${LATENCY_DB}."
}

# Execute SQL against the latency SQLite database.
latency_sqlite_exec() {
    local sql="$1"

    sqlite3 "$LATENCY_DB" "$sql" || fatal "Could not update latency database: ${LATENCY_DB}."
}

# Insert one default latency target when it does not exist yet.
ensure_latency_target() {
    local iface="$1"
    local target="$2"
    local sql

    sql="
        INSERT INTO latency_targets (
            iface, target, count, timeout, enabled, created_at, updated_at
        )
        VALUES (
            $(latency_sql_quote "$iface"),
            $(latency_sql_quote "$target"),
            ${LATENCY_DEFAULT_COUNT},
            ${LATENCY_DEFAULT_TIMEOUT},
            1,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(iface, target) DO UPDATE SET
            enabled = 1,
            updated_at = CURRENT_TIMESTAMP;
    "

    latency_sqlite_exec "$sql"
}

# Ensure the default external latency targets exist for the selected WAN interface.
ensure_default_latency_targets() {
    local iface="$1"
    local target

    [[ -n "$iface" ]] || fatal "WAN interface is required to configure latency targets."
    require_latency_db

    for target in "${LATENCY_DEFAULT_TARGETS[@]}"; do
        ensure_latency_target "$iface" "$target"
    done

    log "Default latency targets were configured for ${iface}: ${LATENCY_DEFAULT_TARGETS[*]}."
}
