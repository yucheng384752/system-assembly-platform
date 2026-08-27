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
[ -d "${SYS_ROOT}" ] || { echo "[ERROR] system/ not found — run deploy.sh first" >&2; exit 1; }
VENV="${SYS_ROOT}/.venv"
[ -f "${VENV}/bin/python" ] || { echo "[ERROR] venv not found — run deploy.sh first" >&2; exit 1; }
mkdir -p "${SYS_ROOT}/logs" "${SYS_ROOT}/runtime"

# Stop a stale backend left over from a previous run, so port 8000 is free
# before we start a new one. Only kill it if the PID is still alive AND is
# actually our uvicorn process. Never touch an unrelated PID that got reused.
PID_FILE="${SYS_ROOT}/runtime/backend.pid"
if [ -f "${PID_FILE}" ]; then
    OLD_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null \
       && ps -p "${OLD_PID}" -o args= 2>/dev/null | grep -q "uvicorn app.main:app"; then
        echo "  Stopping previous backend (PID ${OLD_PID})..."
        kill "${OLD_PID}" 2>/dev/null || true
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            kill -0 "${OLD_PID}" 2>/dev/null || break
            sleep 0.5
        done
        kill -0 "${OLD_PID}" 2>/dev/null && kill -9 "${OLD_PID}" 2>/dev/null || true
    fi
    rm -f "${PID_FILE}"
fi

# This VM is dedicated to running this system, so unlike the pidfile check
# above (which never touches a PID it can't verify is our own uvicorn),
# anything still squatting on port 8000 at this point is assumed safe to
# kill outright.
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ':8000 '; then
    echo "  Port 8000 is occupied; this VM is dedicated to this system, freeing it..."
    OCCUPANT_PIDS="$(ss -tlnp 2>/dev/null | grep ':8000 ' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u)"
    for _p in ${OCCUPANT_PIDS}; do
        echo "  Killing PID ${_p} holding port 8000..."
        kill "${_p}" 2>/dev/null || true
    done
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        ss -tln 2>/dev/null | grep -q ':8000 ' || break
        sleep 0.5
    done
    if ss -tln 2>/dev/null | grep -q ':8000 '; then
        for _p in ${OCCUPANT_PIDS}; do
            kill -9 "${_p}" 2>/dev/null || true
        done
        sleep 0.5
    fi
    if ss -tln 2>/dev/null | grep -q ':8000 '; then
        echo "[ERROR] Port 8000 is still in use after attempting to free it." >&2
        echo "        Check: sudo ss -tlnp | grep :8000" >&2
        exit 1
    fi
fi

(
    cd "${SYS_ROOT}/backend"
    exec nohup "${VENV}/bin/python" -m uvicorn app.main:app \
        --host 127.0.0.1 --port 8000 \
        </dev/null >"${SYS_ROOT}/logs/backend.log" 2>&1
) &
echo "$!" >"${PID_FILE}"
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