#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../common/globals.sh
. "$ROOT_DIR/bin/scripts/common/globals.sh"

# shellcheck source=../common/log.sh
declare -F fatal >/dev/null 2>&1 || . "$ROOT_DIR/bin/scripts/common/log.sh"

SYSTEMD_UNIT_FILE="/etc/systemd/system/armfirewall-supervisord.service"
SYSTEMD_SERVICE_NAME="armfirewall-supervisord.service"

# Stop any existing ArmFirewall supervisord process before systemd owns it.
stop_existing_supervisord() {
    local supervisorctl_bin
    local pid
    local wait_count=0

    supervisorctl_bin="$(command -v supervisorctl || true)"

    if [[ -n "$supervisorctl_bin" && -S "$ROOT_DIR/logs/supervisor.sock" ]]; then
        "$supervisorctl_bin" -c "$SUPERVISORD_CONF" shutdown >/dev/null 2>&1 || true
    fi

    if [[ -f "$ROOT_DIR/logs/supervisord.pid" ]]; then
        pid="$(cat "$ROOT_DIR/logs/supervisord.pid" 2>/dev/null || true)"
        if [[ -n "$pid" && -d "/proc/$pid" ]]; then
            while [[ -d "/proc/$pid" && "$wait_count" -lt 15 ]]; do
                sleep 1
                wait_count=$((wait_count + 1))
            done
            [[ ! -d "/proc/$pid" ]] || fatal "Could not stop existing ArmFirewall supervisord process: ${pid}."
        fi
    fi

    rm -f "$ROOT_DIR/logs/supervisor.sock" "$ROOT_DIR/logs/supervisord.pid"
}

# Create the systemd unit responsible for running ArmFirewall supervisord.
create_systemd_unit() {
    local supervisord_bin
    local supervisorctl_bin

    supervisord_bin="$(command -v supervisord || true)"
    supervisorctl_bin="$(command -v supervisorctl || true)"

    [[ -n "$supervisord_bin" ]] || fatal "supervisord was not found."
    [[ -n "$supervisorctl_bin" ]] || fatal "supervisorctl was not found."

    cat > "$SYSTEMD_UNIT_FILE" <<UNIT
[Unit]
Description=ArmFirewall supervisord service manager
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
ExecStartPre=${ROOT_DIR}/bin/armfwinit.sh
ExecStart=${supervisord_bin} -c ${SUPERVISORD_CONF}
ExecReload=${supervisorctl_bin} -c ${SUPERVISORD_CONF} reload
ExecStop=${supervisorctl_bin} -c ${SUPERVISORD_CONF} shutdown
PIDFile=${ROOT_DIR}/logs/supervisord.pid
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
UNIT

    chmod 0644 "$SYSTEMD_UNIT_FILE"

    if command -v systemctl >/dev/null 2>&1; then
        systemctl daemon-reload
    fi

    log "Created systemd unit: ${SYSTEMD_UNIT_FILE}."
}

# Enable and start the ArmFirewall supervisord systemd service.
enable_and_start_systemd_unit() {
    command -v systemctl >/dev/null 2>&1 || fatal "systemctl was not found."

    systemctl enable "$SYSTEMD_SERVICE_NAME" >/dev/null || \
        fatal "Could not enable ${SYSTEMD_SERVICE_NAME}."

    systemctl restart "$SYSTEMD_SERVICE_NAME" || \
        fatal "Could not start ${SYSTEMD_SERVICE_NAME}."

    log "Enabled and started systemd service: ${SYSTEMD_SERVICE_NAME}."
}

# Create the supervisord configuration used by ArmFirewall services.
create_supervisord_conf() {
    mkdir -p "$CONF_DIR" "$ROOT_DIR/logs"

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

[program:armfirewall-api]
directory=$ROOT_DIR
command=$ROOT_DIR/.venv/bin/uvicorn web.main:app --app-dir $ROOT_DIR --host 0.0.0.0 --port 8000 --ssl-keyfile $ROOT_DIR/conf/armfirewall.key --ssl-certfile $ROOT_DIR/conf/armfirewall.crt
user=armfw
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=$ROOT_DIR/logs/armfirewall-api.out.log
stdout_logfile_maxbytes=5MB
stdout_logfile_backups=5
stderr_logfile=$ROOT_DIR/logs/armfirewall-api.err.log
stderr_logfile_maxbytes=5MB
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED="1"

[program:armfirewall-ifaced]
directory=$ROOT_DIR
command=$ROOT_DIR/.venv/bin/python -m daemons.ifaced.ifaced
user=armfw
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=$ROOT_DIR/logs/armfirewall-ifaced.out.log
stdout_logfile_maxbytes=5MB
stdout_logfile_backups=5
stderr_logfile=$ROOT_DIR/logs/armfirewall-ifaced.err.log
stderr_logfile_maxbytes=5MB
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED="1"

[program:armfirewall-monitord]
directory=$ROOT_DIR
command=$ROOT_DIR/.venv/bin/python -m daemons.monitord
user=armfw
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=$ROOT_DIR/logs/armfirewall-monitord.out.log
stdout_logfile_maxbytes=5MB
stdout_logfile_backups=5
stderr_logfile=$ROOT_DIR/logs/armfirewall-monitord.err.log
stderr_logfile_maxbytes=5MB
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED="1"

[program:armfirewall-workreqd]
directory=$ROOT_DIR
command=$ROOT_DIR/.venv/bin/python -m daemons.workreqd.workreqd
user=armfw
autostart=true
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile=$ROOT_DIR/logs/armfirewall-workreqd.out.log
stdout_logfile_maxbytes=5MB
stdout_logfile_backups=5
stderr_logfile=$ROOT_DIR/logs/armfirewall-workreqd.err.log
stderr_logfile_maxbytes=5MB
stderr_logfile_backups=5
environment=PYTHONUNBUFFERED="1"

SUPERVISOR

    log "Created supervisord configuration: ${SUPERVISORD_CONF}."
}

# Create required service manager files for ArmFirewall.
main() {
    create_supervisord_conf
    create_systemd_unit
    stop_existing_supervisord
    enable_and_start_systemd_unit
}

main "$@"
