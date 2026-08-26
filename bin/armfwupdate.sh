#!/usr/bin/env bash
# Update an ArmFirewall installation from its configured GitHub origin.
set -Eeuo pipefail

readonly EXPECTED_REPOSITORY="github.com/daniel-armbrust/armfirewall-proj"
readonly START_TIMEOUT_SECONDS=60

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=scripts/common/globals.sh
. "$SCRIPT_DIR/scripts/common/globals.sh"

ROOT_DIR=""
FORCE_UPDATE=0
SUPERVISORCTL=""

usage() {
    cat <<'USAGE'
    
Usage: armfwupdate.sh --root-dir <installation-directory> [--force]

Options:
  --root-dir <directory>  ArmFirewall installation directory to update (required).
  --force                 Overwrite locally modified tracked files.
  -h, --help              Show this help message.

The installation must be a checkout whose origin is
github.com/daniel-armbrust/armfirewall-proj.git. Only fast-forward updates are
accepted. Programs that were RUNNING before the update are restarted one by one
and each one must return to RUNNING before the next restart begins.

--force does not remove untracked files, so runtime databases, logs, certificates,
and generated configuration remain in place.
USAGE
}

fatal() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

info() {
    printf '[armfwupdate] %s\n' "$*"
}

parse_args() {
    while (($#)); do
        case "$1" in
            --root-dir)
                (($# >= 2)) || fatal "--root-dir requires a directory."
                ROOT_DIR="$2"
                shift 2
                ;;
            --force)
                FORCE_UPDATE=1
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                fatal "Unknown option: $1"
                ;;
        esac
    done

    [[ -n "$ROOT_DIR" ]] || fatal "Missing required option: --root-dir <installation-directory>."
}

normalise_repository_url() {
    local url="$1"

    url="${url%.git}"
    url="${url#https://}"
    url="${url#http://}"
    url="${url#ssh://}"
    url="${url#git@}"
    url="${url/:/\/}"
    printf '%s\n' "${url%/}"
}

find_supervisorctl() {
    if [[ -x "$ROOT_DIR/.venv/bin/supervisorctl" ]]; then
        SUPERVISORCTL="$ROOT_DIR/.venv/bin/supervisorctl"
    elif command -v supervisorctl >/dev/null 2>&1; then
        SUPERVISORCTL="$(command -v supervisorctl)"
    else
        fatal "supervisorctl was not found."
    fi
}

capture_running_programs() {
    local status_output program

    "$SUPERVISORCTL" -c "$ROOT_DIR/conf/supervisord.conf" pid >/dev/null 2>&1 ||
        fatal "Could not connect to supervisord."

    status_output="$("$SUPERVISORCTL" -c "$ROOT_DIR/conf/supervisord.conf" status 2>&1 || true)"
    [[ -n "$status_output" ]] ||
        fatal "Could not obtain supervisord program status."

    while IFS= read -r program; do
        [[ -n "$program" ]] && running_programs+=("$program")
    done < <(awk '$2 == "RUNNING" { print $1 }' <<<"$status_output")
}

wait_for_running() {
    local program="$1"
    local status_line state elapsed

    for ((elapsed = 0; elapsed < START_TIMEOUT_SECONDS; elapsed++)); do
        status_line="$("$SUPERVISORCTL" -c "$ROOT_DIR/conf/supervisord.conf" status "$program" 2>&1 || true)"
        state="$(awk 'NR == 1 { print $2 }' <<<"$status_line")"

        if [[ "$state" == "RUNNING" ]]; then
            return 0
        fi

        sleep 1
    done

    fatal "Program '$program' did not reach RUNNING within ${START_TIMEOUT_SECONDS}s. Last status: $status_line"
}

restart_running_programs() {
    local -a programs=("$@")
    local program

    ((${#programs[@]})) || {
        info "No supervisord program was RUNNING before the update."
        return 0
    }

    for program in "${programs[@]}"; do
        info "Restarting supervisord program: $program"
        "$SUPERVISORCTL" -c "$ROOT_DIR/conf/supervisord.conf" restart "$program"
        wait_for_running "$program"
        info "Program is RUNNING: $program"
    done
}

main() {
    local origin_url normalised_origin branch upstream
    local -a running_programs=()

    print_banner "updater"

    parse_args "$@"

    [[ $EUID -eq 0 ]] || fatal "This script must run as root."
    [[ -d "$ROOT_DIR" ]] || fatal "Installation directory does not exist: $ROOT_DIR"
    ROOT_DIR="$(cd "$ROOT_DIR" && pwd -P)"

    command -v git >/dev/null 2>&1 || fatal "git is required to update ArmFirewall."
    git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
        fatal "Not a Git working tree: $ROOT_DIR"

    origin_url="$(git -C "$ROOT_DIR" remote get-url origin 2>/dev/null)" ||
        fatal "The installation has no 'origin' remote."
    normalised_origin="$(normalise_repository_url "$origin_url")"
    [[ "$normalised_origin" == "$EXPECTED_REPOSITORY" ]] ||
        fatal "Unexpected origin remote: $origin_url"

    if ((FORCE_UPDATE)); then
        info "Force mode enabled: locally modified tracked files will be overwritten."
    else
        git -C "$ROOT_DIR" diff --quiet ||
        fatal "The installation has modified tracked files. Re-run with --force to overwrite them."
    git -C "$ROOT_DIR" diff --cached --quiet ||
        fatal "The installation has staged tracked files. Re-run with --force to overwrite them."
    fi

    branch="$(git -C "$ROOT_DIR" symbolic-ref --quiet --short HEAD)" ||
        fatal "The checkout is detached; switch to a tracked branch first."
    upstream="origin/$branch"

    find_supervisorctl

    info "Fetching updates for branch '$branch'."
    git -C "$ROOT_DIR" fetch --prune origin

    git -C "$ROOT_DIR" rev-parse --verify --quiet "$upstream" >/dev/null ||
        fatal "Remote branch not found: $upstream"

    if git -C "$ROOT_DIR" diff --quiet HEAD "$upstream"; then
        info "ArmFirewall is already up to date."
        return 0
    fi

    git -C "$ROOT_DIR" merge-base --is-ancestor HEAD "$upstream" ||
        fatal "Local branch is not a fast-forward ancestor of $upstream."

    capture_running_programs
    info "Applying fast-forward update."
    if ((FORCE_UPDATE)); then
        git -C "$ROOT_DIR" reset --hard "$upstream"
    else
        git -C "$ROOT_DIR" merge --ff-only "$upstream"
    fi

    restart_running_programs "${running_programs[@]}"
    info "Update completed successfully."
}

main "$@"

