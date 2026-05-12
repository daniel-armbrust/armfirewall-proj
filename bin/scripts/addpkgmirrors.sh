#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=scripts/globals.sh
. "$ROOT_DIR/bin/scripts/globals.sh"

OS_ID="" 
OS_VERSION_ID="" 
OS_MAJOR="" 
OS_MINOR="" 
ARCH="$(uname -m)" 

# Checks which package manager should be used according to the Linux 
# version
load_os() {
    [[ -r /etc/os-release ]] || fatal "/etc/os-release was not found."
    
    . /etc/os-release
    
    OS_ID="${ID:-unknown}"
    OS_VERSION_ID="${VERSION_ID:-}"
    OS_MAJOR="${OS_VERSION_ID%%.*}"
    
    [[ "$OS_VERSION_ID" == *.* ]] && OS_MINOR="${OS_VERSION_ID#*.}" || OS_MINOR="0"
    
    if has_cmd dnf; then 
        PKG_MANAGER=dnf; 
    elif has_cmd apt-get; then 
        PKG_MANAGER=apt; 
    else 
        fatal "No supported package manager was found."; 
    fi

    log "Detected OS: id=${OS_ID}, version=${OS_VERSION_ID}, major=${OS_MAJOR}, minor=${OS_MINOR}, arch=${ARCH}, package_manager=${PKG_MANAGER}."
}

# Creates a timestamped backup of a file or directory when it exists
backup_path() {
    local path="$1" stamp

    if [[ -e "$path" ]]; then
        stamp="$(date '+%Y%m%d%H%M%S')"
        cp -a "$path" "${path}.armfirewall.${stamp}.bak"
        log "Backed up ${path}."
    fi
}

# Validates whether an HTTP/HTTPS URL is reachable without downloading 
# its content
http_head() {
    local url="$1"

    if has_cmd curl; then
        curl -fsIL --connect-timeout 10 --retry 2 "$url" >/dev/null
    elif has_cmd python3; then
        python3 - "$url" <<'PY'
import sys
from urllib.request import Request, urlopen
with urlopen(Request(sys.argv[1], method="HEAD"), timeout=10) as r:
    raise SystemExit(0 if r.status < 400 else r.status)
PY
    else
        fatal "curl or python3 is required to validate repository URLs."
    fi
}

# Validates whether a package repository metadata URL is reachable 
# before enabling the repository
validate_repo() {
    local name="$1" 
    local base_url="$2" 
    local metadata_url="${base_url%/}/repodata/repomd.xml"
    
    log "Validating ${name}: ${metadata_url}"
    
    # Validates whether an HTTP/HTTPS URL is reachable without 
    # downloading its content
    http_head "$metadata_url"
}

# Configures validated DNF/YUM repositories and refreshes package metadata
write_dnf_repos() {
    local repo_dir=/etc/yum.repos.d
    local temp_repo

    mkdir -p "$repo_dir"
    temp_repo="$(mktemp)"
    trap 'rm -f "${temp_repo:-}"' RETURN

    case "$OS_ID" in
        ol|oracle|oraclelinux)
            local base="https://yum.oracle.com/repo/OracleLinux/OL${OS_MAJOR}/baseos/latest/\$basearch/"
            local appstream="https://yum.oracle.com/repo/OracleLinux/OL${OS_MAJOR}/appstream/\$basearch/"
            local epel

            if [[ "$OS_MAJOR" -ge 10 ]]; then
                epel="https://yum.oracle.com/repo/OracleLinux/OL${OS_MAJOR}/${OS_MINOR}/developer/EPEL/\$basearch/"
            else
                epel="https://yum.oracle.com/repo/OracleLinux/OL${OS_MAJOR}/developer/EPEL/\$basearch/"
            fi

            # Validates whether a package repository metadata URL is reachable 
            # before enabling the repository
            validate_repo "Oracle Linux BaseOS" "${base//\$basearch/$ARCH}" || fatal "Invalid Oracle Linux BaseOS repository URL."
            validate_repo "Oracle Linux AppStream" "${appstream//\$basearch/$ARCH}" || fatal "Invalid Oracle Linux AppStream repository URL."
            validate_repo "Oracle Linux EPEL" "${epel//\$basearch/$ARCH}" || fatal "Invalid Oracle Linux EPEL repository URL. The repository was not enabled."

            cat > "$temp_repo" <<REPO
[ol${OS_MAJOR}_baseos_latest]
name=Oracle Linux ${OS_MAJOR} BaseOS Latest
baseurl=${base}
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-oracle

[ol${OS_MAJOR}_appstream]
name=Oracle Linux ${OS_MAJOR} AppStream
baseurl=${appstream}
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-oracle

[ol${OS_MAJOR}_developer_EPEL]
name=Oracle Linux ${OS_MAJOR} Developer EPEL
baseurl=${epel}
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-oracle
REPO
            ;;

        rhel|rocky|almalinux|centos)
            cat > "$temp_repo" <<REPO
[epel]
name=Extra Packages for Enterprise Linux ${OS_MAJOR}
metalink=https://mirrors.fedoraproject.org/metalink?repo=epel-${OS_MAJOR}&arch=\$basearch&infra=stock
enabled=1
gpgcheck=0
REPO
            log "Vendor base repositories were preserved through package manager metadata; EPEL was configured."
            ;;

        fedora)
            cat > "$temp_repo" <<REPO
[fedora]
name=Fedora Everything ${OS_MAJOR}
metalink=https://mirrors.fedoraproject.org/metalink?repo=fedora-${OS_MAJOR}&arch=\$basearch
enabled=1
gpgcheck=1

[updates]
name=Fedora Updates ${OS_MAJOR}
metalink=https://mirrors.fedoraproject.org/metalink?repo=updates-released-f${OS_MAJOR}&arch=\$basearch
enabled=1
gpgcheck=1
REPO
            ;;

        *) fatal "Unsupported dnf distribution: ${OS_ID}." ;;
    esac

    # Creates a timestamped backup of a file or directory when it exists
    backup_path "$repo_dir"

    find "$repo_dir" -maxdepth 1 -type f -name '*.repo' -exec mv {} {}.armfirewall.disabled \;

    case "$OS_ID" in
        ol|oracle|oraclelinux) 
            install -m 0644 "$temp_repo" "$repo_dir/armfirewall-oraclelinux.repo" 
            ;;

        fedora) 
            install -m 0644 "$temp_repo" "$repo_dir/armfirewall-fedora.repo" 
            ;;

        *) 
            install -m 0644 "$temp_repo" "$repo_dir/armfirewall-epel.repo" 
            ;;
    esac

	log "Refreshing dnf metadata after repository validation."
	
    [[ -r /etc/pki/rpm-gpg/RPM-GPG-KEY-oracle ]] && rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-oracle || true
	
    dnf clean all || true
	dnf -y makecache
    
    rm -f "$temp_repo"
    
    trap - RETURN
}

# Configures APT repositories for Debian-like systems and refreshes 
# package metadata
write_apt_repos() {
    local codename=""

    . /etc/os-release
    codename="${VERSION_CODENAME:-}"

    [[ -n "$codename" ]] || fatal "Unable to detect Debian/Ubuntu codename."

    backup_path /etc/apt/sources.list
    mkdir -p /etc/apt/sources.list.d

    find /etc/apt/sources.list.d -maxdepth 1 -type f -name '*.list' -exec mv {} {}.armfirewall.disabled \;
    : > /etc/apt/sources.list

    if [[ "$OS_ID" == ubuntu ]]; then
        cat > /etc/apt/sources.list.d/armfirewall.list <<APT
deb http://archive.ubuntu.com/ubuntu ${codename} main universe multiverse restricted
deb http://archive.ubuntu.com/ubuntu ${codename}-updates main universe multiverse restricted
deb http://security.ubuntu.com/ubuntu ${codename}-security main universe multiverse restricted
APT
    else
        cat > /etc/apt/sources.list.d/armfirewall.list <<APT
deb http://deb.debian.org/debian ${codename} main contrib non-free non-free-firmware
deb http://deb.debian.org/debian ${codename}-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security ${codename}-security main contrib non-free non-free-firmware
APT
    fi

    apt-get update
}

main() {
    # Checks which package manager should be used according to the Linux version
    load_os

    case "$PKG_MANAGER" in 
        dnf) 
            write_dnf_repos ;; 
        apt) 
            write_apt_repos ;; 
    esac
    
    log "Package repositories were configured successfully."
}
main "$@"
