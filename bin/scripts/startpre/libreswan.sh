#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# Render managed Libreswan files from the persisted SQLite state before
# supervisord starts the Libreswan program.
main() {
    local python_bin

    [[ -f "$LIBRESWAN_DB" ]] || {
        log "Skipping Libreswan pre-start because database was not found: ${LIBRESWAN_DB}."
        return 0
    }
    sqlite_table_exists "$LIBRESWAN_DB" "libreswan_connections" || {
        log "Skipping Libreswan pre-start because libreswan_connections table was not found."
        return 0
    }

    if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
        python_bin="$ROOT_DIR/.venv/bin/python"
    else
        python_bin="$(command -v python3 || true)"
    fi
    [[ -n "$python_bin" ]] || fatal "python3 is required to render persisted Libreswan state."

    log "Rendering persisted Libreswan configuration."
    export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
    (cd "$ROOT_DIR" && "$python_bin" -m daemons.libreswand.libreswand --render-only)
}

main "$@"
