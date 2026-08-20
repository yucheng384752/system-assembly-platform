#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ENV_FILE="${ROOT}/.env"

get_env_value() {
    local key="$1"
    if [ -f "${ENV_FILE}" ]; then
        grep -E "^${key}=" "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2- || true
    fi
}

if [ ! -f "${ENV_FILE}" ]; then
    echo "WARNING: .env not found at ${ENV_FILE}; upload validation runtime settings were not checked." >&2
fi

for key in VALID_MATERIALS_CSV VALID_SLITTING_MACHINES_CSV; do
    value="$(get_env_value "${key}")"
    if [ -z "${value// }" ]; then
        echo "WARNING: ${key} is missing or empty in .env." >&2
    fi
done
