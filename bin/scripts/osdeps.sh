#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
LAST_LOG=""
ARMFIREWALL_LOG_CONTEXT="$(basename "$0")"
PKG_MANAGER=""

# shellcheck source=log.sh
. "$ROOT_DIR/bin/scripts/log.sh"

has_cmd() { 
    command -v "$1" >/dev/null 2>&1; 
}

need_root() { 
    [[ ${EUID:-$(id -u)} -eq 0 ]] || fatal "This script must be run as root."; 
}

identify_pm() { 
    if has_cmd dnf; then 
        PKG_MANAGER=dnf; 
    elif has_cmd apt-get; then 
        PKG_MANAGER=apt; 
    else 
        fatal "No supported package manager was found."; 
    fi; 
    
    log "Using package manager: ${PKG_MANAGER}."; 
}

capture_run() { 
    local f

    f="$(mktemp)"; 
    
    set +e; "$@" > >(tee "$f") 2>&1; local s=$?; set -e; LAST_LOG="$f"; return "$s"; 
}

clean_dnf_cache() { 
    log "Cleaning dnf caches and rebuilding metadata."; 
    dnf clean packages || true; dnf clean metadata || true; dnf makecache; 
}

sync_system_clock() {
    if has_cmd chronyc; then
        log "Synchronizing system clock with chrony before package transactions."
        chronyc makestep || true
    elif has_cmd timedatectl; then
        log "Enabling NTP before package transactions."
        timedatectl set-ntp true || true
    fi
}

repair_dnf_gpg_or_cache() {
    local f="$1"

    grep -Eqi 'GPG check FAILED|Problem opening package|Header V[0-9]+ RSA/SHA|signature.*(failed|BAD)' "$f" || return 1

    log "Detected dnf GPG/cache failure; clearing package cache and refreshing trusted keys."

    if grep -Eqi 'signature is not alive|Not live until' "$f"; then
        log "Detected RPM signature newer than system clock; forcing time synchronization."
        sync_system_clock
    fi

    if [[ -r /etc/pki/rpm-gpg/RPM-GPG-KEY-oracle ]]; then
        rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-oracle || true
    fi

    dnf clean all || true
    rm -rf /var/cache/dnf/*
    dnf makecache
}

fix_fips_conflict() {
    local f="$1"

    grep -Eqi 'fips\.so|openssl-fips-provider|openssl-fips-provider-so|Transaction test error' "$f" || return 1
    rpm -q openssl-fips-provider-so >/dev/null 2>&1 || return 1
    
    log "Detected OpenSSL FIPS provider conflict; removing legacy openssl-fips-provider-so."
    
    if ! dnf -y remove openssl-fips-provider-so; then
        log "dnf refused to remove openssl-fips-provider-so; applying rpm --nodeps fallback only for this known conflict."
        rpm -e --nodeps openssl-fips-provider-so
    fi

    clean_dnf_cache
}

remove_detected_conflict() {
    local f="$1" pkg=""

    pkg="$(grep -Eio 'conflicts between attempted installs of [^ ]+ and [^ ]+' "$f" | awk '{print $NF}' | sed 's/[,:]$//' | head -n1 || true)"
    
    [[ -n "$pkg" ]] || return 1
    
    rpm -q "$pkg" >/dev/null 2>&1 || return 1
    
    log "Removing conflicting installed package before retrying: ${pkg}."
    
    dnf -y remove "$pkg" || rpm -e --nodeps "$pkg"
    
    clean_dnf_cache
}

run_dnf_transaction() {
    local op="$1"; shift

    log "Running dnf ${op}: $*"

    if capture_run dnf -y "$op" "$@"; then 
        rm -f "$LAST_LOG"; 
        return 0; 
    fi

    log "dnf ${op} failed; applying corrective actions."
    
    fix_fips_conflict "$LAST_LOG" || remove_detected_conflict "$LAST_LOG" || repair_dnf_gpg_or_cache "$LAST_LOG" || clean_dnf_cache
    
    log "Retrying dnf ${op} with --allowerasing --best."
    
    if capture_run dnf -y --allowerasing --best "$op" "$@"; then 
        rm -f "$LAST_LOG"; return 0; 
    fi

    fix_fips_conflict "$LAST_LOG" || remove_detected_conflict "$LAST_LOG" || repair_dnf_gpg_or_cache "$LAST_LOG" || clean_dnf_cache

    log "Retrying dnf ${op} with --allowerasing --skip-broken."

    capture_run dnf -y --allowerasing --skip-broken "$op" "$@" || fatal "dnf ${op} failed after corrective actions."

    rm -f "$LAST_LOG"
}

run_apt_transaction() {
    local op="$1"; shift

    log "Running apt-get ${op}: $*"

    DEBIAN_FRONTEND=noninteractive apt-get -y "$op" "$@" || { 
        log "Repairing apt dependencies and retrying."; 
        DEBIAN_FRONTEND=noninteractive apt-get -f install -y || true; 
        apt-get clean || true; 
        apt-get update; 
        DEBIAN_FRONTEND=noninteractive 
        apt-get -y "$op" "$@"; 
    }
}

disable_selinux() {
    log "Disabling SELinux."

    has_cmd setenforce && setenforce 0 || true
    
    [[ -f /etc/selinux/config ]] && sed -i.bak -E 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config || true
}

install_system_deps() {
    case "$PKG_MANAGER" in
        dnf)
            sync_system_clock
            run_dnf_transaction upgrade
            run_dnf_transaction install ethtool python3 python3-pip net-tools supervisor sqlite tar perl curl openssl rrdtool traceroute mtr tcpdump dnsmasq
            ;;
        apt)
            apt-get update
            run_apt_transaction upgrade
            run_apt_transaction install ethtool python3 python3-pip net-tools supervisor sqlite3 tar perl curl openssl python3-venv rrdtool traceroute mtr tcpdump dnsmasq
            ;;
    esac
}

create_python_env() {
    log "Creating Python virtual environment at ${VENV_DIR}."
    
    python3 -m venv "$VENV_DIR"
    . "$VENV_DIR/bin/activate"
    python -m pip install --upgrade pip
    python -m pip install -r "$ROOT_DIR/requirements.txt"
}

main() { 
    need_root; 
    identify_pm; 
    disable_selinux; 
    install_system_deps; 
    create_python_env; 
    log "ArmFirewall dependencies were installed successfully."; 
}

main "$@"
