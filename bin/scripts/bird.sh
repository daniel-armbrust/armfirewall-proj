#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
GLOBALS_FILE="${SCRIPT_DIR}/common/globals.sh"

if [[ ! -r "${GLOBALS_FILE}" ]]; then
    echo "error: ArmFirewall globals file was not found: ${GLOBALS_FILE}" >&2
    exit 1
fi

source "${GLOBALS_FILE}" >/dev/null

if [[ -z "${ROOT_DIR:-}" ]]; then
    echo "error: ROOT_DIR was not defined by ${GLOBALS_FILE}" >&2
    exit 1
fi

PYTHON_BIN="${ARMFW_PYTHON:-}"

if [[ -z "${PYTHON_BIN}" ]]; then
    if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
        PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
    elif command -v python3.12 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3.12)"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    else
        echo "error: no compatible Python interpreter was found." >&2
        exit 1
    fi
fi

if ! "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    echo "error: ${PYTHON_BIN} must be Python 3.9 or newer." >&2
    exit 1
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/py/bird.py" "$@"
