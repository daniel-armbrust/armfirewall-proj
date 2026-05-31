#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

NSS_DIR="/etc/ipsec.d"

# Libreswan requires a valid NSS database before pluto can start. Keep this
# repair local to pre-start so installed/enabled Libreswan survives reboots.
initialize_nss_db() {
    log "Initializing Libreswan NSS database in ${NSS_DIR}."
    if command -v ipsec >/dev/null 2>&1 && ipsec initnss --nssdir "$NSS_DIR" >/dev/null 2>&1; then
        return 0
    fi

    if command -v certutil >/dev/null 2>&1; then
        certutil -N -d "sql:${NSS_DIR}" --empty-password >/dev/null 2>&1 && return 0
    fi

    return 1
}

nss_db_files_exist() {
    compgen -G "${NSS_DIR}/cert*.db" >/dev/null || \
    compgen -G "${NSS_DIR}/key*.db" >/dev/null || \
    [[ -f "${NSS_DIR}/pkcs11.txt" || -f "${NSS_DIR}/secmod.db" ]]
}

backup_nss_db_files() {
    local backup_dir
    local file
    local moved=0

    backup_dir="${NSS_DIR}.armfw-backup-$(date +%Y%m%d%H%M%S)"
    mkdir -p "$backup_dir"
    for file in "$NSS_DIR"/cert*.db "$NSS_DIR"/key*.db "$NSS_DIR"/pkcs11.txt "$NSS_DIR"/secmod.db; do
        [[ -e "$file" ]] || continue
        mv "$file" "$backup_dir/"
        moved=1
    done
    [[ "$moved" -eq 0 ]] || log "Backed up invalid Libreswan NSS database files to ${backup_dir}."
}

ensure_nss_db() {
    mkdir -p "$NSS_DIR"

    if command -v certutil >/dev/null 2>&1 && certutil -L -d "sql:${NSS_DIR}" >/dev/null 2>&1; then
        return 0
    fi

    if ! nss_db_files_exist; then
        initialize_nss_db || fatal "Could not initialize Libreswan NSS database in ${NSS_DIR}."
        return 0
    fi

    command -v certutil >/dev/null 2>&1 || \
        fatal "certutil is required to validate existing Libreswan NSS database files in ${NSS_DIR}."
    backup_nss_db_files
    initialize_nss_db || fatal "Could not repair Libreswan NSS database in ${NSS_DIR}."
}

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
    ensure_nss_db
}

main "$@"
