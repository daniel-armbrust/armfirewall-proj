#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF_FILE="$ROOT_DIR/conf/armfw.conf"
SUPERVISORD_CONF="$ROOT_DIR/conf/supervisord.conf"
HOMEFIREWALL_LOG_CONTEXT="$(basename "$0")"

# shellcheck source=scripts/log.sh
. "$ROOT_DIR/bin/scripts/log.sh"

# shellcheck source=scripts/fwrules.sh
. "$ROOT_DIR/bin/scripts/fwrules.sh"

# shellcheck source=scripts/proutes.sh
. "$ROOT_DIR/bin/scripts/proutes.sh"

# shellcheck source=scripts/latency.sh
. "$ROOT_DIR/bin/scripts/latency.sh"

# Ensure the script is running with root privileges.
need_root() { 
    [[ ${EUID:-$(id -u)} -eq 0 ]] || fatal "This script must be run as root."; 
}

# Run repository, dependency, and database bootstrap scripts.
run_bootstrap_scripts() { 
    "$ROOT_DIR/bin/scripts/addpkgmirrors.sh"; 
    "$ROOT_DIR/bin/scripts/osdeps.sh"; 
    "$ROOT_DIR/bin/scripts/execddl.sh"; 
}

# Detect the Linux distribution family from os-release metadata.
os_family() {
    local os_id="" os_like=""

    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        os_id="${ID:-}"
        os_like="${ID_LIKE:-}"
    fi

    case "${os_id} ${os_like}" in
        *ol*|*oracle*|*rhel*|*fedora*|*centos*|*rocky*|*almalinux*)
            printf 'redhat'
            ;;
        *debian*|*ubuntu*)
            printf 'debian'
            ;;
        *)
            printf 'unknown'
            ;;
    esac
}

# Check whether a systemd service exists on this host.
systemd_service_known() {
    local service="$1"

    command -v systemctl >/dev/null 2>&1 || return 1
    systemctl list-unit-files "${service}.service" >/dev/null 2>&1 && return 0
    systemctl status "${service}.service" >/dev/null 2>&1 && return 0

    return 1
}

# Stop and disable a firewall service when it is present.
disable_firewall_service() {
    local service="$1"

    systemd_service_known "$service" || return 0

    if systemctl is-active --quiet "$service"; then
        log "Stopping OS firewall service: ${service}."
        systemctl stop "$service" || fatal "Could not stop OS firewall service: ${service}."
    fi

    if systemctl is-active --quiet "$service"; then
        fatal "OS firewall service is still active after stop attempt: ${service}."
    fi

    if systemctl is-enabled --quiet "$service" 2>/dev/null; then
        log "Disabling OS firewall service: ${service}."
        systemctl disable "$service" >/dev/null 2>&1 || fatal "Could not disable OS firewall service: ${service}."
    fi

    if systemctl is-enabled --quiet "$service" 2>/dev/null; then
        fatal "OS firewall service is still enabled after disable attempt: ${service}."
    fi
}

# Disable known OS firewall services before applying HomeFirewall rules.
disable_os_firewall_services() {
    local family service

    family="$(os_family)"
    log "Detected firewall service family: ${family}."

    case "$family" in
        redhat)
            for service in firewalld nftables iptables ip6tables; do
                disable_firewall_service "$service"
            done
            ;;
        debian)
            for service in ufw nftables netfilter-persistent iptables-persistent; do
                disable_firewall_service "$service"
            done
            ;;
        *)
            for service in firewalld ufw nftables netfilter-persistent iptables-persistent iptables ip6tables; do
                disable_firewall_service "$service"
            done
            ;;
    esac
}

# Return the first IPv4 or global IPv6 address with prefix length for an interface.
interface_ip_mask() {
    local iface="$1"
    local ip_mask

    ip_mask="$(ip -o -4 addr show dev "$iface" 2>/dev/null | awk '{print $4}' | paste -sd ',' -)"

    if [[ -z "$ip_mask" ]]; then
        ip_mask="$(ip -o -6 addr show dev "$iface" scope global 2>/dev/null | awk '{print $4}' | paste -sd ',' -)"
    fi

    [[ -n "$ip_mask" ]] || ip_mask="-"
    printf '%s\n' "$ip_mask"
}

# Return the MAC address for an interface.
interface_mac_address() {
    local iface="$1"
    local mac_address

    mac_address="$(cat "/sys/class/net/${iface}/address" 2>/dev/null || true)"
    [[ -n "$mac_address" ]] || mac_address="-"
    printf '%s\n' "$mac_address"
}

# Return whether an interface is currently UP or DOWN.
interface_status() {
    local iface="$1"

    if [[ "$(cat "/sys/class/net/${iface}/operstate" 2>/dev/null || true)" == "up" ]]; then
        printf 'UP\n'
    else
        printf 'DOWN\n'
    fi
}

# Read a single key value from the HomeFirewall configuration file.
get_conf_value() {
    local key="$1"

    [[ -f "$CONF_FILE" ]] || return 0
    awk -F= -v key="$key" '
        $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
            value=$2
            sub(/^[[:space:]]+/, "", value)
            sub(/[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONF_FILE"
}

# Write or update a single key value in the HomeFirewall configuration file.
set_conf_value() {
    local key="$1"
    local value="$2"
    local tmp_file

    mkdir -p "$(dirname "$CONF_FILE")"
    tmp_file="$(mktemp "${CONF_FILE}.XXXXXX")"

    if [[ -f "$CONF_FILE" ]]; then
        awk -F= -v key="$key" -v value="$value" '
            BEGIN { found=0 }
            $1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
                print key "=" value
                found=1
                next
            }
            { print }
            END {
                if (!found) {
                    print key "=" value
                }
            }
        ' "$CONF_FILE" > "$tmp_file"
    else
        printf '%s=%s\n' "$key" "$value" > "$tmp_file"
    fi

    mv "$tmp_file" "$CONF_FILE"
}

# Build the selectable interface list, optionally excluding one interface.
load_interface_choices() {
    local excluded_iface="${1:-}"
    local iface

    INTERFACE_CHOICES=()
    while IFS= read -r iface; do
        [[ -n "$iface" ]] || continue
        [[ "$iface" == "lo" ]] && continue
        [[ -n "$excluded_iface" && "$iface" == "$excluded_iface" ]] && continue
        INTERFACE_CHOICES+=("$iface")
    done < <(ip -o link show | awk -F': ' '{print $2}' | cut -d'@' -f1)
}

# Print the available interfaces for an interactive role selection.
list_interfaces() {
    local role="$1"
    local excluded_iface="${2:-}"
    local idx=1
    local iface

    load_interface_choices "$excluded_iface"

    if [[ "${#INTERFACE_CHOICES[@]}" -eq 0 ]]; then
        fatal "No network interfaces were found for ${role} selection."
    fi

    log "Available ${role} interface choices:"
    printf '\nSelect the %s interface by number:\n' "$role" >&2
    printf '  %-4s %-12s %-20s %-19s %s\n' 'No.' 'Interface' 'IP/Mask' 'MAC Address' 'Status' >&2
    printf '  %-4s %-12s %-20s %-19s %s\n' '---' '---------' '-------' '-----------' '------' >&2

    for iface in "${INTERFACE_CHOICES[@]}"; do
        printf '  %-4s %-12s %-20s %-19s %s\n' \
            "${idx})" \
            "$iface" \
            "$(interface_ip_mask "$iface")" \
            "$(interface_mac_address "$iface")" \
            "$(interface_status "$iface")" >&2
        idx=$((idx + 1))
    done

    printf '\n' >&2
}

# Read and persist one interface choice for the requested role.
read_interface_choice() {
    local role="$1"
    local conf_key="$2"
    local excluded_iface="${3:-}"
    local iface=""
    local selected_option=""
    local selected_index
    local max_option

    iface="$(get_conf_value "$conf_key")"

    if [[ -n "$iface" && -n "$excluded_iface" && "$iface" == "$excluded_iface" ]]; then
        log_warn "Configured ${role} interface ${iface} cannot be the same as ${excluded_iface}; asking again."
        iface=""
    fi

    if [[ -n "$iface" && "$iface" == "lo" ]]; then
        log_warn "Configured ${role} interface cannot be loopback; asking again."
        iface=""
    fi

    if [[ -n "$iface" ]] && ! ip link show dev "$iface" >/dev/null 2>&1; then
        log_warn "Configured ${role} interface ${iface} was not found; asking again."
        iface=""
    fi

    if [[ -z "$iface" ]]; then
        while true; do
            list_interfaces "$role" "$excluded_iface"
            max_option="${#INTERFACE_CHOICES[@]}"

            printf 'Type the number of the %s interface [1-%s]: ' "$role" "$max_option" >&2
            read -r selected_option

            if [[ ! "$selected_option" =~ ^[0-9]+$ ]]; then
                log_warn "Invalid selection '${selected_option}'. Please type only the interface number."
                continue
            fi

            selected_index=$((selected_option - 1))

            if (( selected_index < 0 || selected_index >= max_option )); then
                log_warn "Selection out of range: ${selected_option}. Choose a number from 1 to ${max_option}."
                continue
            fi

            iface="${INTERFACE_CHOICES[$selected_index]}"
            break
        done

        set_conf_value "$conf_key" "$iface"
        log "${role} interface saved to ${CONF_FILE}: ${iface}."
    fi

    printf '%s\n' "$iface"
}

# Read the configured LAN interface or ask the user to select it.
read_lan_iface() {
    read_interface_choice LAN lan_iface
}

# Read the configured WAN interface or ask the user to select it.
read_wan_iface() {
    local lan_iface="$1"

    read_interface_choice WAN wan_iface "$lan_iface"
}

# Return the client IP address for the current SSH session, when available.
current_ssh_client_ip() {
    awk '{print $1; exit}' <<< "${SSH_CONNECTION:-}"
}

# Return the local server IP address used by the current SSH session.
current_ssh_server_ip() {
    awk '{print $3; exit}' <<< "${SSH_CONNECTION:-}"
}

# Return the interface that owns a local IP address.
interface_for_local_ip() {
    local ip_addr="$1"

    [[ -n "$ip_addr" ]] || return 1
    ip -o addr show | awk -v ip_addr="$ip_addr" '
        {
            split($4, addr, "/")
            if (addr[1] == ip_addr) {
                print $2
                exit
            }
        }
    '
}

# Return the route output interface used to reach an IP address.
route_interface_for_ip() {
    local ip_addr="$1"

    [[ -n "$ip_addr" ]] || return 1
    ip route get "$ip_addr" 2>/dev/null | awk '
        {
            for (idx = 1; idx <= NF; idx++) {
                if ($idx == "dev" && (idx + 1) <= NF) {
                    print $(idx + 1)
                    exit
                }
            }
        }
    '
}

# Stop startup when SSH would be locked out by LAN-only management rules.
ensure_ssh_session_uses_lan() {
    local lan_iface="$1"
    local client_ip
    local server_ip
    local ssh_iface
    local route_iface

    client_ip="$(current_ssh_client_ip)"
    server_ip="$(current_ssh_server_ip)"
    [[ -n "$client_ip" && -n "$server_ip" ]] || return 0

    ssh_iface="$(interface_for_local_ip "$server_ip")"
    if [[ -z "$ssh_iface" ]]; then
        log_warn "Could not map current SSH local address ${server_ip} to an interface; falling back to route lookup for ${client_ip}."
        ssh_iface="$(route_interface_for_ip "$client_ip")"
    fi

    if [[ -z "$ssh_iface" ]]; then
        log_warn "Could not detect the interface used by current SSH session; continuing without SSH lockout validation."
        return 0
    fi

    route_iface="$(route_interface_for_ip "$client_ip" || true)"
    log "Current SSH session uses local address ${server_ip} on interface ${ssh_iface}."

    if [[ -n "$route_iface" && "$route_iface" != "$ssh_iface" ]]; then
        log_warn "Route lookup for SSH client ${client_ip} points to ${route_iface}; keeping validation based on local address interface ${ssh_iface}."
    fi

    if [[ "$ssh_iface" != "$lan_iface" ]]; then
        fatal "Refusing to rebuild firewall: current SSH session uses local interface ${ssh_iface}, but management access is allowed only on LAN interface ${lan_iface}."
    fi
}

# Resolve the NetworkManager connection name for an interface.
nmcli_connection_for_interface() {
    local iface="$1"
    local connection

    connection="$(nmcli -g GENERAL.CONNECTION device show "$iface" 2>/dev/null | awk 'NF {print; exit}')"
    if [[ -z "$connection" || "$connection" == "--" ]]; then
        connection="$iface"
    fi

    printf '%s\n' "$connection"
}

# Prefer the selected LAN interface for its directly connected IPv4 network.
prefer_lan_connected_route() {
    local lan_iface="$1"
    local connection
    local lan_addr
    local lan_ip
    local lan_network

    lan_addr="$(ip -o -4 addr show dev "$lan_iface" 2>/dev/null | awk '{print $4; exit}')"
    [[ -n "$lan_addr" ]] || return 0

    lan_ip="${lan_addr%%/*}"
    lan_network="$(ip -4 route show dev "$lan_iface" proto kernel scope link 2>/dev/null | awk 'NF {print $1; exit}')"
    [[ -n "$lan_network" ]] || return 0

    log "Preferring LAN interface ${lan_iface} for connected network ${lan_network}."

    if command -v nmcli >/dev/null 2>&1; then
        connection="$(nmcli_connection_for_interface "$lan_iface")"
        nmcli connection modify "$connection" ipv4.never-default yes ipv4.route-metric 10 >/dev/null 2>&1 || true
        nmcli device reapply "$lan_iface" >/dev/null 2>&1 || true
    fi

    ip -4 route replace "$lan_network" dev "$lan_iface" proto static scope link src "$lan_ip" metric 10 || \
        fatal "Could not prefer LAN connected route ${lan_network} through ${lan_iface}."
}

# Prevent non-WAN NetworkManager connections from installing default routes.
disable_default_routes_on_non_wan_connections() {
    local wan_iface="$1"
    local name type device

    while IFS=: read -r name type device; do
        [[ "$type" == "802-3-ethernet" ]] || continue
        [[ -n "$device" && "$device" != "--" ]] || continue
        [[ "$device" != "$wan_iface" ]] || continue

        log "Disabling default routes on non-WAN interface ${device}."
        nmcli connection modify "$name" ipv4.never-default yes ipv6.never-default yes || \
            fatal "Could not disable default routes on connection ${name}."
        nmcli device reapply "$device" >/dev/null 2>&1 || true
    done < <(nmcli -t -f NAME,TYPE,DEVICE connection show)
}

# Configure DHCP on the WAN interface using the best available tool.
enable_dhcp_on_wan() {
    local wan_iface="$1"
    local connection

    ip link set "$wan_iface" up || fatal "Could not bring WAN interface ${wan_iface} up."

    if ! command -v nmcli >/dev/null 2>&1; then
        log "NetworkManager was not found; trying a DHCP client directly on WAN interface ${wan_iface}."

        if command -v dhclient >/dev/null 2>&1; then
            dhclient -4 -r "$wan_iface" >/dev/null 2>&1 || true
            dhclient -4 -v "$wan_iface" >/dev/null 2>&1 || fatal "dhclient could not configure DHCP on ${wan_iface}."
            return 0
        fi

        if command -v dhcpcd >/dev/null 2>&1; then
            dhcpcd -4 "$wan_iface" >/dev/null 2>&1 || fatal "dhcpcd could not configure DHCP on ${wan_iface}."
            return 0
        fi

        if command -v udhcpc >/dev/null 2>&1; then
            udhcpc -i "$wan_iface" -q >/dev/null 2>&1 || fatal "udhcpc could not configure DHCP on ${wan_iface}."
            return 0
        fi

        fatal "No supported DHCP tool was found for WAN interface ${wan_iface}."
    fi

    connection="$(nmcli_connection_for_interface "$wan_iface")"
    log "Enabling DHCP on WAN interface ${wan_iface} using NetworkManager connection ${connection}."

    if ! nmcli connection show "$connection" >/dev/null 2>&1; then
        nmcli connection add type ethernet ifname "$wan_iface" con-name "$connection" \
            ipv4.method auto ipv4.never-default no ipv6.method ignore >/dev/null || \
            fatal "Could not create NetworkManager connection for WAN interface ${wan_iface}."
    fi

    disable_default_routes_on_non_wan_connections "$wan_iface"

    nmcli connection modify "$connection" \
        connection.autoconnect yes \
        ipv4.method auto \
        ipv4.never-default no \
        ipv4.route-metric 500 \
        ipv4.gateway "" \
        ipv4.addresses "" \
        ipv4.dns "" \
        ipv6.method ignore >/dev/null || \
        fatal "Could not configure DHCP on WAN connection ${connection}."

    nmcli connection up "$connection" ifname "$wan_iface" >/dev/null || \
        fatal "Could not activate DHCP on WAN interface ${wan_iface}."
}

# Remove all IPv4 default routes from the main routing table.
flush_default_routes() {
    log "Removing all IPv4 default routes from the main routing table."
    ip -4 route flush default || fatal "Could not remove IPv4 default routes."
}

# Discover the DHCP gateway assigned to the WAN interface.
dhcp_gateway_for_wan() {
    local wan_iface="$1"
    local gateway=""
    local attempt

    for attempt in {1..20}; do
        if command -v nmcli >/dev/null 2>&1; then
            gateway="$(nmcli -g IP4.GATEWAY device show "$wan_iface" 2>/dev/null | awk 'NF {print; exit}')"
            if [[ -n "$gateway" ]]; then
                printf '%s\n' "$gateway"
                return 0
            fi
        fi

        gateway="$(ip -4 route show default dev "$wan_iface" 2>/dev/null | awk '/^default / {print $3; exit}')"
        if [[ -n "$gateway" ]]; then
            printf '%s\n' "$gateway"
            return 0
        fi

        sleep 1
    done

    return 1
}

# Rebuild the main default route using the WAN DHCP gateway.
configure_main_default_route() {
    local wan_iface="$1"
    local gateway

    if [[ "$wan_iface" == *[[:space:]]* ]]; then
        fatal "Only one WAN interface is allowed. Current value: ${wan_iface}."
    fi

    flush_default_routes
    enable_dhcp_on_wan "$wan_iface"

    gateway="$(dhcp_gateway_for_wan "$wan_iface")" || \
        fatal "Could not determine DHCP gateway for WAN interface ${wan_iface}."

    log "Setting the only IPv4 default route through ${gateway} on WAN interface ${wan_iface}."

    flush_default_routes

    ip -4 route replace default via "$gateway" dev "$wan_iface" || \
        fatal "Could not set IPv4 default route through ${gateway} on ${wan_iface}."

    set_conf_value wan_gateway "$gateway"
}

# Write the supervisord configuration used by HomeFirewall services.
ensure_supervisord_conf() {
    mkdir -p "$ROOT_DIR/conf" "$ROOT_DIR/logs"

    cat > "$SUPERVISORD_CONF" <<SUPERVISOR
[unix_http_server]
file=$ROOT_DIR/logs/supervisor.sock
chmod=0700

[supervisord]
logfile=$ROOT_DIR/logs/supervisord.log
logfile_maxbytes=20MB
logfile_backups=5
pidfile=$ROOT_DIR/logs/supervisord.pid
childlogdir=$ROOT_DIR/logs
nodaemon=false

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix://$ROOT_DIR/logs/supervisor.sock

[program:homefirewall-api]
directory=$ROOT_DIR
command=$ROOT_DIR/.venv/bin/uvicorn main:app --app-dir $ROOT_DIR --host 0.0.0.0 --port 8000
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=$ROOT_DIR/logs/homefirewall-api.out.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile=$ROOT_DIR/logs/homefirewall-api.err.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED="1"

[program:homefirewall-ifaced]
directory=$ROOT_DIR
command=$ROOT_DIR/.venv/bin/python $ROOT_DIR/daemons/ifaced.py
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=$ROOT_DIR/logs/homefirewall-ifaced.out.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile=$ROOT_DIR/logs/homefirewall-ifaced.err.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED="1"

[program:homefirewall-monitord]
directory=$ROOT_DIR
command=$ROOT_DIR/.venv/bin/python $ROOT_DIR/daemons/monitord/monitord.py
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=$ROOT_DIR/logs/homefirewall-monitord.out.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile=$ROOT_DIR/logs/homefirewall-monitord.err.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED="1"

[program:homefirewall-workreqd]
directory=$ROOT_DIR
command=$ROOT_DIR/.venv/bin/python $ROOT_DIR/daemons/workreqd.py
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=$ROOT_DIR/logs/homefirewall-workreqd.out.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile=$ROOT_DIR/logs/homefirewall-workreqd.err.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED="1"
SUPERVISOR
}

# Start supervisord with the HomeFirewall configuration when needed.
start_supervisord() { 
    if ! command -v supervisord >/dev/null 2>&1; then 
        fatal "supervisord was not found."; 
    fi

    ensure_supervisord_conf

    if pgrep -x supervisord >/dev/null 2>&1; then
        log "supervisord is already running."
    else
        log "Starting supervisord with ${SUPERVISORD_CONF}."
        supervisord -c "$SUPERVISORD_CONF"
    fi
}

# Create a minimal FastAPI application if the main module is missing.
ensure_fastapi_app() { 
    [[ -f "$ROOT_DIR/main.py" ]] && return 0; 
    
    cat > "$ROOT_DIR/main.py" <<'PY'
from fastapi import FastAPI

app = FastAPI(title="HomeFirewall")

@app.get("/health")
def health():
    return {"status": "ok"}
PY
}

# Ensure the FastAPI service is registered and running under supervisord.
start_uvicorn() { 
    ensure_fastapi_app
    start_supervisord

    if ! command -v supervisorctl >/dev/null 2>&1; then
        fatal "supervisorctl was not found."
    fi

    log "Ensuring HomeFirewall API is managed by supervisord."
    supervisorctl -c "$SUPERVISORD_CONF" reread >/dev/null
    supervisorctl -c "$SUPERVISORD_CONF" update >/dev/null

    if supervisorctl -c "$SUPERVISORD_CONF" status homefirewall-api 2>/dev/null | grep -Eq 'RUNNING|STARTING'; then
        log "HomeFirewall API is already managed by supervisord."
        return 0
    fi

    supervisorctl -c "$SUPERVISORD_CONF" start homefirewall-api >/dev/null || fatal "Could not start HomeFirewall API with supervisord."
}

# Run the complete startup flow for interfaces, routing, firewall, and services.
main() { 
    local lan_iface
    local wan_iface

    need_root 
    run_bootstrap_scripts 

    lan_iface="$(read_lan_iface)"
    wan_iface="$(read_wan_iface "$lan_iface")"
    ensure_default_latency_targets "$wan_iface"
    ensure_ssh_session_uses_lan "$lan_iface"

    prefer_lan_connected_route "$lan_iface"
    configure_main_default_route "$wan_iface"
    prefer_lan_connected_route "$lan_iface"
    sync_policy_routing_db

    initialize_firewall_rules
    allow_lan_services "$lan_iface"
    allow_forward_to_wan "$lan_iface" "$wan_iface"
    configure_masquerade "$wan_iface"
    apply_persisted_filter_rules
    HOMEFIREWALL_BOOTSTRAP=1 set_default_policies
    
    start_uvicorn
}

main "$@"
