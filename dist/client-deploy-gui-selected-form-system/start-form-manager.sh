#!/usr/bin/env bash
# Start gui-selected-form-system
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" ; pwd)"

if command -v docker >/dev/null 2>&1 && [ -f "${SCRIPT_DIR}/docker-compose.yml" ]; then
    docker compose -f "${SCRIPT_DIR}/docker-compose.yml" up -d
    echo "  Services started.  Frontend: http://localhost"
    exit 0
fi

SYS_ROOT="${SCRIPT_DIR}/system"
[ -d "${SYS_ROOT}" ] || { echo "[ERROR] system/ not found ??run deploy.sh first" >&2; exit 1; }
VENV="${SYS_ROOT}/.venv"
[ -f "${VENV}/bin/python" ] || { echo "[ERROR] venv not found ??run deploy.sh first" >&2; exit 1; }
mkdir -p "${SYS_ROOT}/logs" "${SYS_ROOT}/runtime"
(cd "${SYS_ROOT}/backend" && \
nohup "${VENV}/bin/python" -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 \
    </dev/null >"${SYS_ROOT}/logs/backend.log" 2>&1 &
echo "$!" >"${SYS_ROOT}/runtime/backend.pid")
echo "  Backend started.  API: http://127.0.0.1:8000"

# Bring up nginx too (frontend + /api/ reverse proxy), if it was configured
# by the install wizard / deploy.sh. Best-effort: a start script failure
# here should not be treated as the backend failing to start.
if command -v nginx >/dev/null 2>&1 && [ -f /etc/nginx/sites-available/form-system ]; then
    if systemctl is-active --quiet nginx 2>/dev/null; then
        echo "  Frontend:         http://localhost  (nginx already running)"
    elif sudo systemctl start nginx 2>/dev/null; then
        echo "  Frontend:         http://localhost  (nginx started)"
    else
        echo "  [WARN] nginx is configured but could not be started automatically."
        echo "         Run: sudo systemctl start nginx"
    fi
else
    echo "  Frontend:         http://localhost  (nginx not configured yet, see README.md Troubleshooting, or re-run the install wizard)"
fi