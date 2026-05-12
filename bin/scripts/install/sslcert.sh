#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CONF_DIR="$ROOT_DIR/conf"
CERT_FILE="$CONF_DIR/armfirewall.crt"
KEY_FILE="$CONF_DIR/armfirewall.key"
ARMFIREWALL_LOG_CONTEXT="$(basename "$0")"

# shellcheck source=../common/log.sh
. "$ROOT_DIR/bin/scripts/common/log.sh"

# Return a DNS-safe hostname for the certificate subject.
cert_hostname() {
    hostname -f 2>/dev/null || hostname 2>/dev/null || printf 'armfirewall'
}

# Write the OpenSSL configuration used to include SAN entries.
write_openssl_config() {
    local config_file="$1"
    local hostname_value="$2"
    local san_index=3
    local ip_addr

    cat > "$config_file" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = ${hostname_value}
O = ArmFirewall
OU = Web GUI

[v3_req]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = ${hostname_value}
DNS.2 = localhost
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

    while IFS= read -r ip_addr; do
        [[ -n "$ip_addr" ]] || continue
        printf 'IP.%s = %s\n' "$san_index" "$ip_addr" >> "$config_file"
        san_index=$((san_index + 1))
    done < <(ip -o addr show scope global 2>/dev/null | awk '{split($4, a, "/"); print a[1]}' | sort -u)
}

# Return success when the current certificate is still usable.
certificate_is_valid() {
    [[ -s "$CERT_FILE" && -s "$KEY_FILE" ]] || return 1
    openssl x509 -checkend 2592000 -noout -in "$CERT_FILE" >/dev/null 2>&1
}

# Apply restrictive permissions to TLS files.
set_tls_permissions() {
    [[ -e "$KEY_FILE" ]] && chmod 0400 "$KEY_FILE"
    [[ -e "$CERT_FILE" ]] && chmod 0400 "$CERT_FILE"
}

# Generate the self-signed certificate used by Uvicorn.
generate_certificate() {
    local config_file
    local hostname_value

    command -v openssl >/dev/null 2>&1 || fatal "openssl is required to generate the ArmFirewall TLS certificate."

    mkdir -p "$CONF_DIR"
    chmod 700 "$CONF_DIR"

    if certificate_is_valid; then
        set_tls_permissions
        log "TLS certificate already exists and is valid: ${CERT_FILE}."
        return 0
    fi

    hostname_value="$(cert_hostname)"
    config_file="$(mktemp)"
    write_openssl_config "$config_file" "$hostname_value"

    log "Generating ArmFirewall self-signed TLS certificate in ${CONF_DIR}."
    openssl req \
        -x509 \
        -nodes \
        -newkey rsa:2048 \
        -days 3650 \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -config "$config_file" >/dev/null 2>&1 || {
            rm -f "$config_file"
            fatal "Could not generate ArmFirewall TLS certificate."
        }

    rm -f "$config_file"
    set_tls_permissions
    log "TLS certificate generated: ${CERT_FILE}."
}

# Run the TLS certificate bootstrap flow.
main() {
    generate_certificate
}

main "$@"
