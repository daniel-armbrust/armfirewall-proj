#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=scripts/globals.sh
. "$ROOT_DIR/bin/scripts/globals.sh"

DDL_DIR="$ROOT_DIR/db/ddl"
DB_DIR="$ROOT_DIR/db"

main() {
    command -v sqlite3 >/dev/null 2>&1 || fatal "sqlite3 is required to execute DDL files."
    
    mkdir -p "$DB_DIR"
    shopt -s nullglob

    local ddl found=0 db
    
    for ddl in "$DDL_DIR"/*.ddl; do
        found=1
        
        db="$DB_DIR/$(basename "$ddl" .ddl).db"
        
        log "Applying ${ddl} to ${db}."
        
        sqlite3 "$db" < "$ddl"
    done
    
    [[ "$found" -eq 1 ]] && log "DDL execution completed successfully." || log "No DDL files were found."
}

main "$@"