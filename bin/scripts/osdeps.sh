#!/usr/bin/env bash
set -Eeuo pipefail

VENV_DIR="$ROOT_DIR/.venv"
LAST_LOG=""

# Cleans DNF package caches and rebuilds repository metadata
clean_dnf_cache() { 
    log "Cleaning dnf caches and rebuilding metadata."; 
    dnf clean packages || true; dnf clean metadata || true; dnf makecache; 
}

# Repairs DNF GPG signature or cache failures by refreshing 
# trusted keys and metadata
repair_dnf_gpg_or_cache() {
    local f="$1"

    grep -Eqi 'GPG check FAILED|Problem opening package|Header V[0-9]+ RSA/SHA|signature.*(failed|BAD)' "$f" || return 1

    log "Detected dnf GPG/cache failure; clearing package cache and refreshing trusted keys."

    if grep -Eqi 'signature is not alive|Not live until' "$f"; then
        log "Detected RPM signature newer than system clock; forcing time synchronization."
    fi

    if [[ -r /etc/pki/rpm-gpg/RPM-GPG-KEY-oracle ]]; then
        rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-oracle || true
    fi

    dnf clean all || true
    rm -rf /var/cache/dnf/*
    dnf makecache
}

# Detects and removes an installed package that conflicts with the 
# requested DNF transaction
remove_detected_conflict() {
    local f="$1" pkg=""

    pkg="$(grep -Eio 'conflicts between attempted installs of [^ ]+ and [^ ]+' "$f" | awk '{print $NF}' | sed 's/[,:]$//' | head -n1 || true)"
    
    [[ -n "$pkg" ]] || return 1
    
    rpm -q "$pkg" >/dev/null 2>&1 || return 1
    
    log "Removing conflicting installed package before retrying: ${pkg}."
    
    dnf -y remove "$pkg" || rpm -e --nodeps "$pkg"
    
    # Cleans DNF package caches and rebuilds repository metadata
    clean_dnf_cache
}

# Detects and fixes known OpenSSL FIPS provider conflicts during DNF transactions
fix_fips_conflict() {
    local f="$1"

    grep -Eqi 'fips\.so|openssl-fips-provider|openssl-fips-provider-so|Transaction test error' "$f" || return 1
    rpm -q openssl-fips-provider-so >/dev/null 2>&1 || return 1
    
    log "Detected OpenSSL FIPS provider conflict; removing legacy openssl-fips-provider-so."
    
    if ! dnf -y remove openssl-fips-provider-so; then
        log "dnf refused to remove openssl-fips-provider-so; applying rpm --nodeps fallback only for this known conflict."
        rpm -e --nodeps openssl-fips-provider-so
    fi

    # Cleans DNF package caches and rebuilds repository metadata
    clean_dnf_cache
}

# Runs a DNF transaction with corrective retries for cache, GPG, and 
# package conflict failures
run_dnf_transaction() {
    local op="$1"; shift

    log "Running dnf ${op}: $*"

    # capture_run() will run a command while capturing its combined 
    # output for later error analysis.

    if capture_run dnf -y "$op" "$@"; then 
        rm -f "$LAST_LOG"; 
        return 0; 
    fi

    log "dnf ${op} failed; applying corrective actions."
    
    # fix_fips_conflict() detects and fixes known OpenSSL FIPS provider 
    # conflicts during DNF transactions

    # remove_detected_conflict() detects and removes an installed package 
    # that conflicts with the requested DNF transaction.

    # repair_dnf_gpg_or_cache() repairs DNF GPG signature or cache failures 
    # by refreshing trusted keys and metadata

    # clean_dnf_cache() cleans DNF package caches and rebuilds repository 
    # metadata

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

# Runs an APT transaction with dependency repair and retry handling
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

# Installs required operating system packages using the detected package manager
install_system_deps() {
    case "$PKG_MANAGER" in
        dnf)
            run_dnf_transaction upgrade
            run_dnf_transaction install ethtool python3 python3-pip net-tools \
                                supervisor sqlite tar perl curl openssl rrdtool \
                                traceroute mtr tcpdump dnsmasq
            ;;
        apt)
            apt-get update
            run_apt_transaction upgrade
            run_apt_transaction install ethtool python3 python3-pip net-tools \
                                supervisor sqlite3 tar perl curl openssl \
                                python3-venv rrdtool traceroute mtr tcpdump dnsmasq
            ;;
    esac
}

# Creates the Python virtual environment and installs ArmFirewall 
# Python dependencies.
create_python_env() {
    log "Creating Python virtual environment at ${VENV_DIR}."
    
    python3 -m venv "$VENV_DIR"

    . "$VENV_DIR/bin/activate"
    
    python -m pip install --upgrade pip
    python -m pip install -r "$ROOT_DIR/requirements.txt"
}

# Disables SELinux enforcement at runtime and persistently in the system configuration.
disable_selinux() {
    log "Disabling SELinux."

    has_cmd setenforce && setenforce 0 || true
    
    [[ -f /etc/selinux/config ]] && sed -i.bak -E 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config || true
}

main() { 
    # Disables SELinux enforcement at runtime and persistently in the 
    # system configuration
    disable_selinux; 
    
    # Synchronizes the system clock before package transactions to avoid 
    # signature validation errors
    sync_system_clock

    # Installs required operating system packages using the detected 
    # package manager
    install_system_deps; 
    
    # Creates the Python virtual environment and installs ArmFirewall Python 
    # dependencies
    create_python_env; 
    
    log "ArmFirewall dependencies were installed successfully."; 
}

main "$@"
