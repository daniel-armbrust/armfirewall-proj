#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
USER_DB="$ROOT_DIR/db/users.db"
ARMFIREWALL_LOG_CONTEXT="$(basename "$0")"

# shellcheck source=log.sh
. "$ROOT_DIR/bin/scripts/log.sh"

# Return a PBKDF2-SHA256 hash in a self-describing format.
generate_admin_password_hash() {
    local python_bin

    python_bin="$(command -v python3 || true)"
    [[ -n "$python_bin" ]] || fatal "python3 is required to create the initial admin password hash."

    "$python_bin" - <<'PY'
import base64
import hashlib
import secrets

password = b"admin"
iterations = 260000
salt = secrets.token_hex(16)
digest = hashlib.pbkdf2_hmac("sha256", password, salt.encode("utf-8"), iterations)
print(f"pbkdf2_sha256${iterations}${salt}${base64.b64encode(digest).decode('ascii')}")
PY
}

# Ensure the users database and schema are available before inserting users.
ensure_users_schema() {
    [[ -f "$USER_DB" ]] || fatal "Users database was not found: ${USER_DB}."

    local table_count
    table_count="$(sqlite3 "$USER_DB" "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'users';")"
    [[ "$table_count" == "1" ]] || fatal "Users table was not found in ${USER_DB}; run execddl.sh first."
}

# Create the default protected admin user when it does not already exist.
ensure_admin_user() {
    local existing_count
    local password_hash

    existing_count="$(sqlite3 "$USER_DB" "SELECT COUNT(*) FROM users WHERE username = 'admin';")"

    if [[ "$existing_count" != "0" ]]; then
        log "Default admin user already exists; preserving current password."
        sqlite3 "$USER_DB" <<'SQL'
UPDATE users
   SET role = 'admin',
       enabled = 1,
       protected = 1,
       updated_at = CURRENT_TIMESTAMP
 WHERE username = 'admin';
SQL
        return 0
    fi

    password_hash="$(generate_admin_password_hash)"

    sqlite3 "$USER_DB" <<SQL
INSERT INTO users (
     username,
     display_name,
     password_hash,
     password_changed_at,
     must_change_password,
     role,
     enabled,
     protected
) VALUES (
     'admin',
     'ArmFirewall Administrator',
     '${password_hash}',
     CURRENT_TIMESTAMP,
     1,
     'admin',
     1,
     1
);
SQL

    log "Default admin user was created and must change password on first login."
}

# Run the admin user bootstrap flow.
main() {
    command -v sqlite3 >/dev/null 2>&1 || fatal "sqlite3 is required to configure the initial admin user."

    ensure_users_schema
    ensure_admin_user
}

main "$@"
