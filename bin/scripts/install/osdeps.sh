#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=scripts/common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

VENV_DIR="$ROOT_DIR/.venv"
LAST_LOG=""
OS_ID=""
OS_VERSION_ID=""
OS_MAJOR=0

# Load Linux distribution metadata used by package decisions.
load_os_info() {
    [[ -r /etc/os-release ]] || fatal "/etc/os-release was not found."

    . /etc/os-release

    OS_ID="${ID:-unknown}"
    OS_VERSION_ID="${VERSION_ID:-0}"
    OS_MAJOR="${OS_VERSION_ID%%.*}"
    [[ "$OS_MAJOR" =~ ^[0-9]+$ ]] || OS_MAJOR=0
}

# Detect which operating system package manager should be used.
identify_pm() {
    if has_cmd dnf; then
        PKG_MANAGER=dnf
    elif has_cmd apt-get; then
        PKG_MANAGER=apt
    else
        fatal "No supported package manager was found."
    fi

    log "Using package manager: ${PKG_MANAGER}."
}

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
        
        DEBIAN_FRONTEND=noninteractive apt-get -y "$op" "$@"; 
    }
}

# Install APT packages without allowing package post-install scripts to start services.
run_apt_transaction_without_service_start() {
    local policy_path="/usr/sbin/policy-rc.d"
    local backup_path=""
    local status

    if [[ -e "$policy_path" ]]; then
        backup_path="${policy_path}.armfirewall.bak"
        cp -a "$policy_path" "$backup_path"
    fi

    printf '#!/bin/sh\nexit 101\n' > "$policy_path"
    chmod 0755 "$policy_path"

    set +e
    run_apt_transaction "$@"
    status=$?
    set -e

    if [[ -n "$backup_path" ]]; then
        mv "$backup_path" "$policy_path"
    else
        rm -f "$policy_path"
    fi

    return "$status"
}

# Stop and disable OS-managed services that ArmFirewall controls through supervisord.
disable_packaged_armfirewall_services() {
    command -v systemctl >/dev/null 2>&1 || return 0

    if systemctl list-unit-files dnsmasq.service >/dev/null 2>&1; then
        log "Disabling OS-managed dnsmasq service; ArmFirewall manages dnsmasq through supervisord."
        systemctl disable --now dnsmasq.service >/dev/null 2>&1 || true
    fi
}

# Install a Python runtime supported by ArmFirewall.
install_python_runtime() {
    case "$PKG_MANAGER" in
        dnf)
            if [[ "$OS_MAJOR" -le 8 ]]; then
                run_dnf_transaction install python39 python39-pip
            else
                run_dnf_transaction install python3 python3-pip
            fi
            ;;
        apt)
            run_apt_transaction install python3 python3-pip python3-venv
            ;;
    esac
}

# Installs required operating system packages using the detected package manager
install_system_deps() {
    case "$PKG_MANAGER" in
        dnf)
            run_dnf_transaction upgrade
            run_dnf_transaction install ethtool net-tools \
                                supervisor sqlite tar perl curl openssl nss-tools rrdtool \
                                traceroute mtr tcpdump dnsmasq
            install_python_runtime
            ;;
        apt)
            apt-get update
            run_apt_transaction_without_service_start upgrade
            run_apt_transaction_without_service_start install ethtool net-tools iproute2 iptables \
                                                  supervisor sqlite3 tar perl curl openssl libnss3-tools \
                                                  rrdtool traceroute mtr tcpdump dnsmasq ifupdown
            disable_packaged_armfirewall_services
            install_python_runtime
            ;;
    esac
}

# Return success when the first version is greater than or equal to the second.
# NetworkManager versions may contain a distro release suffix, therefore only
# the numeric dotted prefix is considered here.
version_at_least() {
    local actual="$1" required="$2"
    local actual_major actual_minor required_major required_minor

    actual="${actual%%[-+~]*}"
    required="${required%%[-+~]*}"
    IFS=. read -r actual_major actual_minor _ <<<"$actual"
    IFS=. read -r required_major required_minor _ <<<"$required"

    [[ "$actual_major" =~ ^[0-9]+$ && "$actual_minor" =~ ^[0-9]+$ ]] || return 1
    [[ "$required_major" =~ ^[0-9]+$ && "$required_minor" =~ ^[0-9]+$ ]] || return 1

    (( 10#$actual_major > 10#$required_major ||
       (10#$actual_major == 10#$required_major && 10#$actual_minor >= 10#$required_minor) ))
}

# Print the NetworkManager version reported by nmcli.
networkmanager_version() {
    nmcli --version 2>/dev/null | awk 'NR == 1 { print $NF }'
}

# Update NetworkManager through the repositories prepared by addpkgmirrors.sh.
# This deliberately does not install packages built for a different OS release:
# replacing core networking packages from an arbitrary RPM/DEB repository can
# make a remotely installed firewall unreachable.
upgrade_networkmanager_from_configured_repositories() {
    case "$PKG_MANAGER" in
        dnf)
            run_dnf_transaction upgrade NetworkManager
            ;;
        apt)
            apt-get update
            run_apt_transaction_without_service_start install --only-upgrade network-manager
            ;;
    esac
}

# Load the upgraded daemon before nmcli writes prefix-delegation properties.
# The installer runs this before it changes interface profiles, so a brief
# NetworkManager restart cannot leave a partially configured ArmFirewall.
restart_networkmanager_after_upgrade() {
    if has_cmd systemctl && systemctl is-active --quiet NetworkManager.service; then
        log "Restarting NetworkManager to load the upgraded IPv6 delegation support."
        systemctl restart NetworkManager.service || fatal "Could not restart NetworkManager after its upgrade."
    fi
}

# Ensure router-mode IPv6 prefix delegation has the NetworkManager capability
# required by ipv6pd.sh. Hosts that do not use NetworkManager keep using the
# legacy networking backend; ipv6pd.sh will then report that PD is unavailable.
ensure_networkmanager_ipv6_pd_support() {
    local current_version

    [[ "${ROUTER_MODE:-0}" == "1" ]] || return 0

    if ! has_cmd nmcli; then
        log "NetworkManager is not installed; skipping its upgrade. IPv6 prefix delegation requires a NetworkManager backend."
        return 0
    fi

    current_version="$(networkmanager_version)"
    [[ -n "$current_version" ]] || fatal "Could not determine the installed NetworkManager version."

    if version_at_least "$current_version" "$NETWORKMANAGER_MIN_VERSION"; then
        log "NetworkManager ${current_version} supports IPv6 prefix delegation (minimum ${NETWORKMANAGER_MIN_VERSION})."
        return 0
    fi

    log "NetworkManager ${current_version} is older than ${NETWORKMANAGER_MIN_VERSION}; upgrading it from the configured ${PKG_MANAGER} repositories."
    upgrade_networkmanager_from_configured_repositories
    restart_networkmanager_after_upgrade

    current_version="$(networkmanager_version)"
    [[ -n "$current_version" ]] || fatal "NetworkManager upgrade completed but nmcli is no longer available."
    version_at_least "$current_version" "$NETWORKMANAGER_MIN_VERSION" || fatal \
        "Configured repositories provide NetworkManager ${current_version}, but IPv6 prefix delegation requires ${NETWORKMANAGER_MIN_VERSION} or newer. Use an OS/repository release that provides the required version."

    log "NetworkManager was upgraded to ${current_version}; IPv6 prefix delegation is supported."
}

# Return success when a Python binary meets the minimum supported version.
python_version_is_supported() {
    "$1" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 9) else 1)
PY
}

# Select the newest installed Python binary supported by ArmFirewall.
select_python_bin() {
    local candidate

    for candidate in python3.12 python3.11 python3.10 python3.9 python39 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && python_version_is_supported "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done

    fatal "ArmFirewall requires Python 3.9 or newer. Oracle Linux 8 must install python39."
}

# Creates the Python virtual environment and installs ArmFirewall 
# Python dependencies.
create_python_env() {
    local python_bin

    python_bin="$(select_python_bin)"

    log "Creating Python virtual environment at ${VENV_DIR}."
    log "Using Python runtime: $("${python_bin}" --version 2>&1)."
    
    "$python_bin" -m venv "$VENV_DIR"

    . "$VENV_DIR/bin/activate"
    
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install -r "$ROOT_DIR/requirements.txt"
}

# Disables SELinux enforcement at runtime and persistently in the system configuration.
disable_selinux() {
    log "Disabling SELinux."

    has_cmd setenforce && setenforce 0 || true
    
    [[ -f /etc/selinux/config ]] && sed -i.bak -E 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config || true
}

main() { 
    # Load Linux distribution metadata used by package decisions
    load_os_info

    # Detect which operating system package manager should be used
    identify_pm

    # Disables SELinux enforcement at runtime and persistently in the 
    # system configuration
    disable_selinux 
    
    # Synchronizes the system clock before package transactions to avoid 
    # signature validation errors
    sync_system_clock

    # Installs required operating system packages using the detected 
    # package manager
    install_system_deps

    # Router mode with IPv6 prefix delegation requires NetworkManager 1.54+.
    # The update is performed only through the signed repositories configured
    # earlier in the installer.
    ensure_networkmanager_ipv6_pd_support
    
    # Creates the Python virtual environment and installs ArmFirewall Python 
    # dependencies
    create_python_env
    
    log "ArmFirewall dependencies were installed successfully."
}

main "$@"
