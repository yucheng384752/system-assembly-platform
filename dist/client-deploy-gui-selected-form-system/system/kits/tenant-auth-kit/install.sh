#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ENV_FILE="${ROOT}/.env"

get_env_value() {
    local key="$1"
    grep -E "^${key}=" "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2- || true
}

if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: .env not found at ${ENV_FILE}; SECRET_KEY is required for tenant auth." >&2
    exit 1
fi

secret_key="$(get_env_value SECRET_KEY)"
auth_mode="$(get_env_value AUTH_MODE)"
if [ -z "${secret_key// }" ]; then
    echo "ERROR: SECRET_KEY is missing or empty in .env." >&2
    exit 1
fi
if [ -z "${auth_mode// }" ]; then
    echo "WARNING: AUTH_MODE is missing or empty in .env." >&2
fi
