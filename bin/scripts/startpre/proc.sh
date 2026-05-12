#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Apply enabled /proc values stored in proc.db.
apply_proc_settings() {
    local id proc_path desired_value

    [[ -f "$PROC_DB" ]] || {
        log "Skipping missing proc database: ${PROC_DB}."
        return 0
    }

    log "Applying persisted kernel proc settings."

    while IFS=$'\t' read -r id proc_path desired_value; do
        [[ -n "${id:-}" && -n "$proc_path" && -n "$desired_value" ]] || continue
        
        [[ -e "$proc_path" ]] || {
            log "Skipping missing proc path: ${proc_path}."
            continue
        }

        # Change /proc filesystem
        printf '%s\n' "$desired_value" > "$proc_path"
        
        sqlite_exec "$PROC_DB" "
            UPDATE proc
            SET current_value=$(sql_quote "$desired_value"),
                collected_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=${id};
        "
    done < <(
        sqlite_query "$PROC_DB" "
            SELECT id, proc_path, desired_value
            FROM proc
            WHERE enabled = 1
              AND desired_value IS NOT NULL
              AND desired_value <> ''
            ORDER BY category, name;
        "
    )
}

# Apply persisted kernel parameters stored in SQLite.
main() {
    apply_proc_settings
}

main "$@"
