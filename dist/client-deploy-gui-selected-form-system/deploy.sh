#!/usr/bin/env bash
# ================================================================
#  Form System Kit Composer - Server Deploy Script (Linux / macOS)
#  Recipe : gui-selected-form-system
#  Built  : 2026-05-24 02:30
#  Kits   : platform-core-kit, tenant-auth-kit, station-data-link-kit, upload-validation-kit, import-pipeline-kit, query-traceability-kit, analytics-kit, station-admin-kit, audit-edit-kit, logs-ops-kit
#  DB     : postgresql
# ================================================================
#
#  Usage:
#    bash deploy.sh
#    bash deploy.sh --interactive
#    bash deploy.sh /opt/form-system --background
#    bash deploy.sh /opt/form-system --interactive --background

set -euo pipefail

die()  { echo "" >&2; echo "[ERROR] $*" >&2; echo "" >&2; exit 1; }
info() { echo "  $*"; }
ok()   { echo "  OK $*"; }

ASK_AUTH=true
ASK_PDF=false
ASK_VALIDATION=true
SCRIPT_DIR="$(cd "$(dirname "$0")" ; pwd)"
SYS_ROOT=""
BACKGROUND=0
INTERACTIVE=0
VENV=""

for _arg in "$@"; do
    case "$_arg" in
        --background) BACKGROUND=1 ;;
        --interactive) INTERACTIVE=1 ;;
        --*) die "Unknown option: $_arg" ;;
        *) SYS_ROOT="$_arg" ;;
    esac
done

resolve_system_root() {
    if [ -z "${SYS_ROOT}" ]; then
        for _c in "$SCRIPT_DIR/system" "$SCRIPT_DIR/generated-system"; do
            if [ -d "$_c" ]; then SYS_ROOT="$_c"; break; fi
        done
    fi
    [ -n "${SYS_ROOT}" ] || die "Cannot find system dir. Usage: bash deploy.sh /path/to/system"
    [ -d "${SYS_ROOT}" ] || die "Directory not found: ${SYS_ROOT}"
    SYS_ROOT="$(cd "${SYS_ROOT}" ; pwd)"
    [ -f "${SYS_ROOT}/backend/requirements.txt" ] || die "backend/requirements.txt not found. Verify path is the assembled system dir."
}

set_env_value() {
    local key="$1"
    local value="$2"
    local file="${SYS_ROOT}/.env"
    local escaped
    escaped="$(printf '%s' "$value" | sed 's/[\/&]/\\&/g')"
    if grep -q "^${key}=" "$file"; then
        sed -i.bak "s/^${key}=.*/${key}=${escaped}/" "$file"
        rm -f "${file}.bak"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

get_env_value() {
    local key="$1"
    grep -E "^${key}=" "${SYS_ROOT}/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true
}

prompt_value() {
    local key="$1"
    local label="$2"
    local default_value="${3:-}"
    local current answer fallback suffix
    current="$(get_env_value "$key")"
    fallback="${current:-$default_value}"
    suffix=""
    [ -n "$fallback" ] && suffix=" [$fallback]"
    read -r -p "${label}${suffix}: " answer
    answer="${answer:-$fallback}"
    set_env_value "$key" "$answer"
}

generate_secret() {
    python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

prompt_secret() {
    local key="$1"
    local label="$2"
    local allow_generate="${3:-0}"
    local current answer suffix
    current="$(get_env_value "$key")"
    suffix=""
    [ -n "$current" ] && suffix=" [keep existing]"
    if [ "$allow_generate" = "1" ]; then
        read -r -p "${label}${suffix} (enter value, 'g' to generate): " answer
        if [ "$answer" = "g" ]; then
            set_env_value "$key" "$(generate_secret)"
            ok "$key generated"
            return
        fi
        if [ -n "$answer" ]; then
            set_env_value "$key" "$answer"
            return
        fi
    fi
    read -rsp "${label}${suffix}: " answer
    echo ""
    if [ -z "$answer" ] && [ -n "$current" ]; then
        answer="$current"
    fi
    set_env_value "$key" "$answer"
}

configure_env() {
    echo "=== Checking configuration ==="
    if [ ! -f "${SYS_ROOT}/.env" ]; then
        if [ "${INTERACTIVE}" -eq 1 ]; then
            [ -f "${SYS_ROOT}/.env.example" ] || die ".env not found and .env.example is missing."
            cp "${SYS_ROOT}/.env.example" "${SYS_ROOT}/.env"
            ok "Created .env from .env.example"
        else
            die ".env not found. Run: bash deploy.sh --interactive, or copy .env.example to .env and edit it."
        fi
    fi

    if [ "${INTERACTIVE}" -eq 1 ]; then
        echo "=== Database ==="
        prompt_value DB_HOST "Database host" "localhost"
        prompt_value DB_PORT "Database port" "5432"
        prompt_value DB_NAME "Database name" "form_system"
        prompt_value DB_USERNAME "Database username" "form_system"
        prompt_secret DB_PASSWORD "Database password"
        if [ -z "$(get_env_value DATABASE_URL)" ]; then
            set_env_value DATABASE_URL "postgresql+asyncpg://$(get_env_value DB_USERNAME):$(get_env_value DB_PASSWORD)@$(get_env_value DB_HOST):$(get_env_value DB_PORT)/$(get_env_value DB_NAME)"
        fi
        prompt_value DATABASE_URL "DATABASE_URL"
        prompt_secret SECRET_KEY "SECRET_KEY" 1
        prompt_value CORS_ORIGINS "CORS origins" "http://localhost:5173,http://localhost:3000"

        if [ "${ASK_AUTH}" = "true" ]; then
            echo "=== Authentication ==="
            prompt_value AUTH_MODE "Auth mode" "api_key"
            prompt_secret ADMIN_API_KEYS "Admin API keys" 1
            prompt_value BOOTSTRAP_MANAGER_ENABLED "Bootstrap manager enabled" "false"
            prompt_value BOOTSTRAP_MANAGER_TENANT_CODE "Bootstrap manager tenant code" "default"
            prompt_value BOOTSTRAP_MANAGER_USERNAME "Bootstrap manager username" "manager"
            prompt_secret BOOTSTRAP_MANAGER_PASSWORD "Bootstrap manager password"
            prompt_value BOOTSTRAP_MANAGER_MUST_CHANGE_PASSWORD "Bootstrap manager must change password" "true"
        fi

        if [ "${ASK_PDF}" = "true" ]; then
            echo "=== PDF Conversion ==="
            prompt_value PDF_SERVER_URL "PDF server URL"
            prompt_value PDF_SERVER_TIMEOUT_SECONDS "PDF server timeout seconds" "1800"
            prompt_value PDF_SERVER_MAX_CONCURRENT "PDF server max concurrent" "3"
            prompt_value PDF_SERVER_TABLE "PDF server table"
        fi

        if [ "${ASK_VALIDATION}" = "true" ]; then
            echo "=== Upload Validation ==="
            prompt_value VALID_MATERIALS_CSV "Valid materials CSV"
            prompt_value VALID_SLITTING_MACHINES_CSV "Valid slitting machines CSV"
        fi
    fi

    set -a ; . "${SYS_ROOT}/.env" ; set +a
    [ -n "${DATABASE_URL:-}" ] || die "DATABASE_URL not set in .env"
    [ -n "${SECRET_KEY:-}" ] || die "SECRET_KEY not set in .env"
    [ -n "${CORS_ORIGINS:-}" ] || die "CORS_ORIGINS not set in .env"
    ok "Configuration OK"
    echo ""
}

_MISSING=0
check_cmd() {
    if command -v "$1" >/dev/null 2>&1; then
        ok "$1  $($1 --version 2>/dev/null | head -1)"
    else
        info "MISSING: $1  -> $2"
        _MISSING=$((_MISSING + 1))
    fi
}

check_prerequisites() {
    echo "=== Prerequisites ==="
    _MISSING=0
    check_cmd python3 "https://www.python.org/downloads/"
    check_cmd pip3    "installed with Python: python3 -m ensurepip"
    check_cmd node    "https://nodejs.org/"
    check_cmd npm     "installed with Node.js"
    [ "${_MISSING}" -eq 0 ] || die "${_MISSING} required tools missing. Install and retry."
    ok "All prerequisites present"
    echo ""
}

setup_venv() {
    echo "=== Setting up virtual environment ==="
    VENV="${SYS_ROOT}/.venv"
    python3 -m venv --clear "${VENV}" || die "Failed to create venv. Run: sudo apt install python3-venv"
    ok "Virtual environment: ${VENV}"
    echo ""
}

install_backend() {
    echo "=== Installing backend dependencies ==="
    "${VENV}/bin/pip" install --quiet --upgrade pip
    "${VENV}/bin/pip" install -r "${SYS_ROOT}/backend/requirements.txt"
    ok "Backend dependencies installed"
    echo ""
}

run_kit_installs() {
    if [ ! -f "${SYS_ROOT}/kitInstallPlan.json" ]; then
        return
    fi

    echo "=== Running kit installs ==="
    SYS_ROOT="${SYS_ROOT}" python3 - <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

sys_root = Path(os.environ["SYS_ROOT"])
plan_path = sys_root / "kitInstallPlan.json"
with plan_path.open("r", encoding="utf-8-sig") as handle:
    plan = json.load(handle)

for entry in sorted(plan, key=lambda item: item.get("order", 0)):
    kit = entry["kit"]
    script = sys_root / "kits" / kit / "install.sh"
    if not script.exists():
        raise SystemExit(f"Kit install script not found: {script}")
    print(f"Running kit install: {kit}")
    subprocess.run(["bash", str(script), str(sys_root)], check=True)
PY
    ok "Kit installs complete"
    echo ""
}

build_frontend() {
    if [ -f "${SYS_ROOT}/frontend/dist/index.html" ]; then
        ok "Frontend pre-built (dist/index.html present)"
        return
    fi
    if [ -f "${SYS_ROOT}/frontend/package.json" ]; then
        echo "=== Building frontend ==="
        npm --prefix "${SYS_ROOT}/frontend" install --silent
        npm --prefix "${SYS_ROOT}/frontend" run build
        ok "Frontend built -> ${SYS_ROOT}/frontend/dist/"
        echo ""
    fi
}

setup_database() {
    echo "=== Database setup ==="
    if [ -f "${SYS_ROOT}/backend/alembic.ini" ]; then
        (cd "${SYS_ROOT}/backend" ; "${VENV}/bin/python" -m alembic upgrade head)
        ok "Database migration complete"
    else
        _bootstrap="${SYS_ROOT}/backend/app/core/generated_db_bootstrap.py"
        if [ -f "${_bootstrap}" ]; then
            info "Running SQLAlchemy bootstrap (no Alembic)..."
            (cd "${SYS_ROOT}/backend" ; "${VENV}/bin/python" -m app.core.generated_db_bootstrap)
            ok "Database tables created"
        else
            info "No migration tool found; skipping database setup"
        fi
    fi
    echo ""
}

start_backend() {
    echo "=== Deploy complete ==="
    if [ "${BACKGROUND}" -eq 1 ]; then
        mkdir -p "${SYS_ROOT}/logs"
        (cd "${SYS_ROOT}/backend" ; nohup "${VENV}/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >"${SYS_ROOT}/logs/backend.log" 2>&1 &
        echo "$!" >"${SYS_ROOT}/logs/backend.pid")
        ok "Backend started in background on port 8000"
        info "Log : ${SYS_ROOT}/logs/backend.log"
        info "Stop: kill \$(cat ${SYS_ROOT}/logs/backend.pid)"
    else
        info "--- Next steps ---"
        info "Start backend:"
        info "  cd ${SYS_ROOT}/backend && ${VENV}/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    fi
    [ -d "${SYS_ROOT}/frontend/dist" ] && info "Frontend dist: ${SYS_ROOT}/frontend/dist/ (serve via nginx, see README)"
}

resolve_system_root
echo ""
echo "Form System Kit Composer - Deploy"
echo "Recipe  : gui-selected-form-system"
echo "SysRoot : ${SYS_ROOT}"
echo ""

configure_env
check_prerequisites
setup_venv
install_backend
run_kit_installs
build_frontend
setup_database
start_backend

echo ""
echo "------------------------------------------------------"
echo "  WARNING: Production checklist"
echo "------------------------------------------------------"
info "1. Do NOT run as root. Create a system user:"
info "     sudo useradd -r -s /bin/false form-system"
info "2. uvicorn has no TLS. Use a reverse proxy:"
info "     nginx + certbot (Let's Encrypt) or Caddy"
info "3. DATABASE_URL, SECRET_KEY, and ADMIN_API_KEYS must be non-default values"
info "4. ENVIRONMENT=production disables the /docs endpoint"
info "5. Run: pip-audit  and  npm audit  (CVE scan)"
echo ""