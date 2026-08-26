#!/usr/bin/env bash
# ================================================================
#  Form System Kit Composer - Server Deploy Script (Linux / macOS)
#  Recipe : gui-selected-form-system
#  Built  : 2026-08-26 17:08
#  Kits   : platform-core-kit, tenant-auth-kit, station-data-link-kit, upload-validation-kit, import-pipeline-kit, query-traceability-kit, analytics-kit, station-admin-kit, audit-edit-kit, logs-ops-kit, generic-forms-kit
#  DB     : postgresql
# ================================================================
#
#  Usage:
#    bash deploy.sh --wizard                            # Guided install wizard (recommended)
#    bash deploy.sh --interactive                       # Prompt mode
#    bash deploy.sh                                     # Auto mode (requires deploy-init.env or .env)
#    bash deploy.sh --get-machine-id                    # Print machine fingerprint for license binding
#    bash deploy.sh --update-license=/path/license.lic  # Replace license.lic without reinstalling
#    bash deploy.sh /opt/form-system --background
#    bash deploy.sh /opt/form-system --wizard --background

set -euo pipefail

die()  { echo "" >&2; echo "[ERROR] $*" >&2; echo "" >&2; exit 1; }
info() { echo "  $*"; }
ok()   { echo "  OK $*"; }

ASK_AUTH=true
ASK_PDF=false
ASK_VALIDATION=true
HIBA_NODE_ID="${HIBA_NODE_ID:-}"
HIBA_DASHBOARD_URL="${HIBA_DASHBOARD_URL:-}"
HIBA_DASHBOARD_TOKEN="${HIBA_DASHBOARD_TOKEN:-}"
HIBA_CALLBACK_ENABLED="${HIBA_CALLBACK_ENABLED:-true}"
SCRIPT_DIR="$(cd "$(dirname "$0")" ; pwd)"
SYS_ROOT=""
BACKGROUND=0
INTERACTIVE=0
WIZARD=0
CMD_FINGERPRINT=0
CMD_UPDATE_LIC=""
VENV=""

for _arg in "$@"; do
    case "$_arg" in
        --background)        BACKGROUND=1 ;;
        --interactive)       INTERACTIVE=1 ;;
        --wizard)            WIZARD=1; INTERACTIVE=1 ;;
        --get-machine-id)    CMD_FINGERPRINT=1 ;;
        --update-license=*)  CMD_UPDATE_LIC="${_arg#--update-license=}" ;;
        --*)                 die "Unknown option: $_arg" ;;
        *)                   SYS_ROOT="$_arg" ;;
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
    chmod 600 "$file" 2>/dev/null || true
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
    if [ -f "${SCRIPT_DIR}/deploy-init.env" ]; then
        info "Found deploy-init.env ??loading pre-configured credentials..."
        set -a; . "${SCRIPT_DIR}/deploy-init.env"; set +a
        cp "${SCRIPT_DIR}/deploy-init.env" "${SYS_ROOT}/.env"
        ok "Credentials loaded from deploy-init.env"
        return 0
    fi
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

# ?? Wizard helpers ??????????????????????????????????????????????????????????

wizard_welcome() {
    clear 2>/dev/null || true
    echo ""
    echo "================================================================"
    echo "  Form System 摰?蝎暸?"
    echo "  Recipe : gui-selected-form-system"
    echo "  Kits   : platform-core-kit, tenant-auth-kit, station-data-link-kit, upload-validation-kit, import-pipeline-kit, query-traceability-kit, analytics-kit, station-admin-kit, audit-edit-kit, logs-ops-kit, generic-forms-kit"
    echo "================================================================"
    echo ""
    echo "  甇斤移??撘??典???"
    echo "    甇仿? 1嚗?  鞈?摨恍??閮剖?"
    echo "    甇仿? 2嚗?  蝞∠??董?身摰?
    echo "    甇仿? 3嚗?  摰??Ⅱ隤?
    echo ""
    echo "  ?亙歇??deploy-init.env嚗身摰郊撽??芸??仿???
    echo "  ??Ctrl+C ?舫??瘨?
    echo ""
    read -r -p "  ??Enter 蝜潛?..." _dummy
    echo ""
}

_validate_nonempty() {
    local val="$1" label="$2"
    [ -n "$val" ] || { echo "  [!] ${label} 銝??箇征" >&2; return 1; }
}

_validate_port() {
    local val="$1"
    [[ "$val" =~ ^[0-9]+$ ]] && [ "$val" -ge 1 ] && [ "$val" -le 65535 ] || \
        { echo "  [!] ??????1??5535 ??? >&2; return 1; }
}

_validate_password() {
    local val="$1"
    [ ${#val} -ge 8 ] || { echo "  [!] 撖Ⅳ?瑕漲?喳? 8 ???? >&2; return 1; }
}

wizard_step1_db() {
    echo "??[ 甇仿? 1嚗?嚗??澈??? ]??????????????????????????????"
    echo ""
    echo "  ?舀 PostgreSQL嚗??Ｙ憓???
    echo "  ?乩?閮剖? DATABASE_URL嚗頂蝯勗??芸??寧 SQLite嚗??璈葫閰佗???
    echo ""
    local _host _port _name _user _pass
    while true; do
        read -r -p "  鞈?摨思蜓璈?? [localhost]: " _host
        _host="${_host:-localhost}"
        _validate_nonempty "$_host" "銝餅?雿?" && break
    done
    while true; do
        read -r -p "  鞈?摨恍???[5432]: " _port
        _port="${_port:-5432}"
        _validate_port "$_port" && break
    done
    while true; do
        read -r -p "  鞈?摨怠?蝔?[form_system]: " _name
        _name="${_name:-form_system}"
        _validate_nonempty "$_name" "鞈?摨怠?蝔? && break
    done
    while true; do
        read -r -p "  鞈?摨思蝙?刻?[form_system]: " _user
        _user="${_user:-form_system}"
        _validate_nonempty "$_user" "雿輻??蝔? && break
    done
    while true; do
        read -rsp "  鞈?摨怠?蝣? " _pass; echo ""
        _validate_nonempty "$_pass" "撖Ⅳ" && break
    done
    set_env_value DB_HOST     "$_host"
    set_env_value DB_PORT     "$_port"
    set_env_value DB_NAME     "$_name"
    set_env_value DB_USERNAME "$_user"
    set_env_value DB_PASSWORD "$_pass"
    set_env_value DATABASE_URL "postgresql+asyncpg://${_user}:${_pass}@${_host}:${_port}/${_name}"
    ok "鞈?摨怨身摰???
    echo ""
}

wizard_step2_auth() {
    echo "??[ 甇仿? 2嚗?嚗恣?董??]??????????????????????????????"
    echo ""
    echo "  閮剖?蝟餌絞?? Manager 撣唾?嚗蝵脣??臬敺?啣??耨?嫘?
    echo "  擐活?餃敺頂蝯勗?閬?靽格撖Ⅳ??
    echo ""
    local _user _pass _pass2
    while true; do
        read -r -p "  Manager 撣唾??迂 [manager]: " _user
        _user="${_user:-manager}"
        _validate_nonempty "$_user" "撣唾??迂" && break
    done
    while true; do
        read -rsp "  Manager 撖Ⅳ嚗撠?8 蝣潘?: " _pass; echo ""
        _validate_password "$_pass" || continue
        read -rsp "  蝣箄?撖Ⅳ: " _pass2; echo ""
        [ "$_pass" = "$_pass2" ] && break
        echo "  [!] ?拇活撖Ⅳ銝??湛?隢??啗撓?? >&2
    done
    set_env_value BOOTSTRAP_MANAGER_ENABLED              "true"
    set_env_value BOOTSTRAP_MANAGER_TENANT_CODE          "default"
    set_env_value BOOTSTRAP_MANAGER_USERNAME             "$_user"
    set_env_value BOOTSTRAP_MANAGER_PASSWORD             "$_pass"
    set_env_value BOOTSTRAP_MANAGER_MUST_CHANGE_PASSWORD "true"
    ok "Manager 撣唾?閮剖?摰?"
    echo ""
}

wizard_step3_secrets() {
    echo "??[ 甇仿? 3嚗?嚗??券??啗?蝣箄? ]?????????????????????????"
    echo ""
    echo "  SECRET_KEY ?冽 JWT / session ????
    echo "  頛詨 'g' ?航??璈??堆??刻嚗?
    echo ""
    prompt_secret SECRET_KEY "SECRET_KEY" 1
    set_env_value CORS_ORIGINS "http://localhost:5173,http://localhost:3000"
    ok "摰?閮剖?摰?"
    echo ""
}

wizard_summary_confirm() {
    echo "??[ 摰?蝣箄? ]????????????????????????????????????????????"
    echo ""
    echo "  鞈?摨?   : $(get_env_value DB_HOST):$(get_env_value DB_PORT) / $(get_env_value DB_NAME)"
    echo "  DB 雿輻??: $(get_env_value DB_USERNAME)"
    echo "  Manager   : $(get_env_value BOOTSTRAP_MANAGER_USERNAME)"
    echo "  CORS      : $(get_env_value CORS_ORIGINS)"
    echo "  撖Ⅳ      : *** (撌脰身摰?銝＊蝷?"
    echo ""
    local _confirm
    read -r -p "  蝣箄?閮剖?甇?Ⅱ嚗?憪?鋆?[y/N] " _confirm
    echo ""
    case "$_confirm" in
        y|Y|yes|YES) ok "??摰?..." ;;
        *) die "摰?撌脣?瘨???瑁? deploy.sh --wizard" ;;
    esac
}

wizard_configure() {
    if [ -f "${SCRIPT_DIR}/deploy-init.env" ]; then
        info "?菜葫??deploy-init.env嚗??仿?閮剛身摰?.."
        set -a; . "${SCRIPT_DIR}/deploy-init.env"; set +a
        cp "${SCRIPT_DIR}/deploy-init.env" "${SYS_ROOT}/.env"
        ok "Credentials loaded from deploy-init.env"
        echo ""
        return 0
    fi
    [ -f "${SYS_ROOT}/.env.example" ] || die ".env.example not found. Cannot create initial .env."
    cp "${SYS_ROOT}/.env.example" "${SYS_ROOT}/.env"
    wizard_step1_db
    wizard_step2_auth
    wizard_step3_secrets
    wizard_summary_confirm
    set -a; . "${SYS_ROOT}/.env"; set +a
    [ -n "${DATABASE_URL:-}" ] || die "DATABASE_URL not set"
    [ -n "${SECRET_KEY:-}" ]   || die "SECRET_KEY not set"
    ok "Configuration OK"
    echo ""
}

show_license_notice() {
    local _lic="${SYS_ROOT}/license.lic"
    [ -f "${_lic}" ] || return
    if python3 - "${_lic}" <<'PY'
import json, sys
try:
    lic = json.load(open(sys.argv[1]))
    payload = json.loads(lic.get("payload", "{}"))
    if not payload.get("machineFingerprint"):
        sys.exit(1)
except Exception:
    sys.exit(1)
PY
    then
        return
    fi
    echo ""
    echo "  NOTE: License is not bound to this machine."
    echo "  To bind it (prevents license copy to another server):"
    echo "    1. bash deploy.sh --get-machine-id"
    echo "    2. Share the Fingerprint with your vendor."
    echo "    3. bash deploy.sh --update-license=/path/to/new-license.lic"
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
        _npm_cache="${SYS_ROOT}/frontend/.npm-cache"
        _npm_args=""
        if [ -d "${_npm_cache}" ]; then
            _npm_args="--cache ${_npm_cache} --offline"
        fi
        if [ -f "${SYS_ROOT}/frontend/package-lock.json" ]; then
            npm --prefix "${SYS_ROOT}/frontend" ci --silent ${_npm_args}
        else
            npm --prefix "${SYS_ROOT}/frontend" install --silent ${_npm_args}
        fi
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
    if [ "${BACKGROUND}" -eq 1 ]; then
        mkdir -p "${SYS_ROOT}/logs"
        (cd "${SYS_ROOT}/backend" ; nohup "${VENV}/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 </dev/null >"${SYS_ROOT}/logs/backend.log" 2>&1 &
        echo "$!" >"${SYS_ROOT}/logs/backend.pid")
        ok "Backend started in background on port 8000"
        info "Log : ${SYS_ROOT}/logs/backend.log"
        info "Stop: kill \$(cat ${SYS_ROOT}/logs/backend.pid)"
    fi
    echo ""
}

setup_postgres() {
    local db_url
    db_url="$(get_env_value DATABASE_URL)"
    case "$db_url" in
        postgresql*) : ;;
        *) return 0 ;;   # SQLite or unset -> nothing to provision
    esac

    echo "=== PostgreSQL setup ==="

    # Parse postgresql[+driver]://user:pass@host:port/dbname
    # ponytail: assumes password has no URL-encoded special chars; fine for generated creds.
    local _rest _creds _hostpart _hostport db_host db_port db_name db_user db_pass
    _rest="${db_url#*://}"
    _creds="${_rest%%@*}"
    _hostpart="${_rest#*@}"
    db_user="${_creds%%:*}"
    db_pass="${_creds#*:}" ; [ "$db_pass" = "$_creds" ] && db_pass=""
    _hostport="${_hostpart%%/*}"
    db_name="${_hostpart#*/}" ; db_name="${db_name%%\?*}"
    db_host="${_hostport%%:*}"
    db_port="${_hostport#*:}" ; [ "$db_port" = "$_hostport" ] && db_port="5432"
    [ -n "$db_host" ] || db_host="localhost"
    [ -n "$db_name" ] || db_name="form_system"
    [ -n "$db_user" ] || db_user="form_system"

    if [ "$db_host" != "localhost" ] && [ "$db_host" != "127.0.0.1" ]; then
        info "DATABASE_URL targets remote host ${db_host}; skipping local PostgreSQL provisioning."
        echo ""
        return 0
    fi

    if ! command -v psql >/dev/null 2>&1; then
        info "PostgreSQL not found -- installing..."
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update && sudo apt-get install -y postgresql || \
                die "PostgreSQL install failed (offline / no network?). Install it manually or use SQLite (empty DATABASE_URL)."
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y postgresql-server postgresql || die "PostgreSQL install failed."
            sudo postgresql-setup --initdb >/dev/null 2>&1 || true
        elif command -v yum >/dev/null 2>&1; then
            sudo yum install -y postgresql-server postgresql || die "PostgreSQL install failed."
            sudo postgresql-setup initdb >/dev/null 2>&1 || true
        else
            die "Cannot auto-install PostgreSQL. Install it manually, or use SQLite (empty DATABASE_URL)."
        fi
    fi

    sudo systemctl enable --now postgresql >/dev/null 2>&1 || sudo service postgresql start >/dev/null 2>&1 || true

    # Wait until the server accepts connections (native, no extra deps)
    local _ready=1 _i
    for _i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
        if sudo -u postgres psql -tAc 'SELECT 1' >/dev/null 2>&1; then _ready=0; break; fi
        sleep 1
    done
    [ "$_ready" -eq 0 ] || die "PostgreSQL did not become ready. Check: sudo systemctl status postgresql"

    # Create role + database idempotently (single-quote-escape the password)
    local esc_pass
    esc_pass="$(printf '%s' "$db_pass" | sed "s/'/''/g")"
    if [ -n "$db_pass" ]; then
        if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${db_user}'" 2>/dev/null | grep -q 1; then
            sudo -u postgres psql -c "ALTER ROLE \"${db_user}\" WITH LOGIN PASSWORD '${esc_pass}'" >/dev/null
        else
            sudo -u postgres psql -c "CREATE ROLE \"${db_user}\" WITH LOGIN PASSWORD '${esc_pass}'" >/dev/null
        fi
    fi
    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${db_name}'" 2>/dev/null | grep -q 1; then
        sudo -u postgres psql -c "CREATE DATABASE \"${db_name}\" OWNER \"${db_user}\"" >/dev/null
    fi

    ok "PostgreSQL ready -- ${db_user}@${db_host}:${db_port}/${db_name}"
    echo ""
}

setup_nginx() {
    echo "=== nginx setup ==="
    if ! [ -d "${SYS_ROOT}/frontend/dist" ]; then
        info "No frontend/dist found; skipping nginx setup"
        echo ""
        return
    fi

    # Install nginx if missing
    if ! command -v nginx >/dev/null 2>&1; then
        info "nginx not found ??installing..."
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get install -y nginx || die "Failed to install nginx. Run: sudo apt-get install -y nginx"
        elif command -v yum >/dev/null 2>&1; then
            sudo yum install -y nginx || die "Failed to install nginx. Run: sudo yum install -y nginx"
        else
            die "Cannot auto-install nginx. Please install nginx manually then re-run."
        fi
    fi

    # Copy to a dedicated, root-owned web root instead of pointing nginx's root
    # directly at SYS_ROOT. Deploy packages are typically extracted under a
    # user's home directory (commonly mode 750/770), which blocks www-data from
    # traversing into it ??nginx would fail to stat the file (Permission denied),
    # try_files falls back to /index.html, and that fails too, causing an
    # internal redirection cycle.
    WEB_ROOT="/var/www/form-system"
    sudo rm -rf "${WEB_ROOT}"
    sudo cp -r "${SYS_ROOT}/frontend/dist" "${WEB_ROOT}" || die "Failed to copy frontend assets to ${WEB_ROOT}"
    sudo chmod -R a+rX "${WEB_ROOT}"

    NGINX_CONF="/etc/nginx/sites-available/form-system"
    sudo tee "${NGINX_CONF}" > /dev/null <<NGINXEOF
server {
    listen 80;
    server_name _;

    root ${WEB_ROOT};
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location /healthz {
        proxy_pass http://127.0.0.1:8000;
    }
}
NGINXEOF

    sudo ln -sf "${NGINX_CONF}" /etc/nginx/sites-enabled/form-system
    # Remove default site if it conflicts on port 80
    [ -f /etc/nginx/sites-enabled/default ] && sudo rm -f /etc/nginx/sites-enabled/default

    if sudo nginx -t 2>/dev/null; then
        sudo systemctl reload nginx 2>/dev/null || sudo systemctl start nginx 2>/dev/null
        ok "nginx configured ??frontend available at http://localhost"
    else
        info "nginx config test failed. Check: sudo nginx -t"
    fi
    echo ""
}

configure_hiba_node() {
    echo "=== HIBA Node ==="
    if [ -f "${SYS_ROOT}/.env" ]; then
        HIBA_NODE_ID="${HIBA_NODE_ID:-$(get_env_value HIBA_NODE_ID)}"
        HIBA_DASHBOARD_URL="${HIBA_DASHBOARD_URL:-$(get_env_value HIBA_DASHBOARD_URL)}"
        HIBA_DASHBOARD_TOKEN="${HIBA_DASHBOARD_TOKEN:-$(get_env_value HIBA_DASHBOARD_TOKEN)}"
        HIBA_CALLBACK_ENABLED="${HIBA_CALLBACK_ENABLED:-$(get_env_value HIBA_CALLBACK_ENABLED)}"
    fi
    if [ -z "${HIBA_NODE_ID}" ]; then
        if [ -f /etc/machine-id ]; then
            HIBA_NODE_ID="$(tr -d '[:space:]' </etc/machine-id | tr '[:upper:]' '[:lower:]')"
        else
            HIBA_NODE_ID="$(hostname 2>/dev/null || echo hiba-node)"
        fi
    fi
    if [ "${INTERACTIVE}" -eq 1 ]; then
        prompt_value HIBA_NODE_ID "HIBA node id" "${HIBA_NODE_ID}"
        prompt_value HIBA_DASHBOARD_URL "HIBA dashboard URL" "${HIBA_DASHBOARD_URL}"
        prompt_secret HIBA_DASHBOARD_TOKEN "HIBA dashboard token"
        prompt_value HIBA_CALLBACK_ENABLED "HIBA dashboard callback enabled" "${HIBA_CALLBACK_ENABLED:-true}"
        HIBA_NODE_ID="$(get_env_value HIBA_NODE_ID)"
        HIBA_DASHBOARD_URL="$(get_env_value HIBA_DASHBOARD_URL)"
        HIBA_DASHBOARD_TOKEN="$(get_env_value HIBA_DASHBOARD_TOKEN)"
        HIBA_CALLBACK_ENABLED="$(get_env_value HIBA_CALLBACK_ENABLED)"
    else
        [ -n "${HIBA_DASHBOARD_URL}" ] || die "HIBA_DASHBOARD_URL not set. Use deploy-online.sh --interactive or set it in deploy-init.env/system/.env."
        set_env_value HIBA_NODE_ID "${HIBA_NODE_ID}"
        set_env_value HIBA_DASHBOARD_URL "${HIBA_DASHBOARD_URL}"
        set_env_value HIBA_DASHBOARD_TOKEN "${HIBA_DASHBOARD_TOKEN}"
        set_env_value HIBA_CALLBACK_ENABLED "${HIBA_CALLBACK_ENABLED:-true}"
    fi
    ok "HIBA node configured: ${HIBA_NODE_ID}"
    echo ""
}

send_hiba_dashboard_callback() {
    [ "${HIBA_CALLBACK_ENABLED:-true}" = "true" ] || return 0
    [ -n "${HIBA_DASHBOARD_URL:-}" ] || return 0
    echo "=== HIBA Dashboard Callback ==="
    HIBA_NODE_ID="${HIBA_NODE_ID}" HIBA_DASHBOARD_URL="${HIBA_DASHBOARD_URL}" HIBA_DASHBOARD_TOKEN="${HIBA_DASHBOARD_TOKEN:-}" SYS_ROOT="${SYS_ROOT}" python3 - <<'PY' || true
import json
import os
import socket
import time
import urllib.error
import urllib.request

base = os.environ["HIBA_DASHBOARD_URL"].rstrip("/")
url = base + "/api/hiba/nodes/register"
payload = {
    "nodeId": os.environ["HIBA_NODE_ID"],
    "recipe": "gui-selected-form-system",
    "status": "deployed",
    "hostname": socket.gethostname(),
    "systemRoot": os.environ["SYS_ROOT"],
    "timestamp": int(time.time()),
}
data = json.dumps(payload).encode("utf-8")
headers = {"Content-Type": "application/json"}
token = os.environ.get("HIBA_DASHBOARD_TOKEN", "")
if token:
    headers["Authorization"] = "Bearer " + token
req = urllib.request.Request(url, data=data, headers=headers, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"  OK dashboard callback HTTP {resp.status}")
except urllib.error.URLError as exc:
    print(f"  WARN dashboard callback failed: {exc}")
PY
    echo ""
}
# -- early-exit: --get-machine-id -------------------------------------------
if [ "${CMD_FINGERPRINT}" -eq 1 ]; then
    _FP=""
    _SOURCE=""
    _MID=""
    if command -v tpm2_getekcertificate >/dev/null 2>&1; then
        _FP="$(tpm2_getekcertificate --ek-certificate /dev/stdout 2>/dev/null | python3 -c 'import hashlib,sys; data=sys.stdin.buffer.read(); print(hashlib.sha256(data).hexdigest() if data else "")' 2>/dev/null || true)"
        if [ -n "${_FP}" ]; then
            _SOURCE="TPM EK certificate"
        fi
    fi
    if [ -z "${_FP}" ]; then
        if [ ! -f /etc/machine-id ]; then
            die "neither TPM EK certificate nor /etc/machine-id is available."
        fi
        _MID="$(tr -d '[:space:]' </etc/machine-id | tr '[:upper:]' '[:lower:]')"
        _FP="$(printf '%s' "${_MID}" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"
        _SOURCE="/etc/machine-id"
    fi
    echo ""
    echo "  Source      : ${_SOURCE}"
    [ -n "${_MID}" ] && echo "  Machine ID  : ${_MID}"
    echo "  Fingerprint : ${_FP}"
    echo ""
    echo "  Share the Fingerprint with your vendor to bind the license."
    echo "  The vendor re-signs license.lic with your Fingerprint."
    echo "  To apply the new license file:"
    echo "    bash deploy.sh --update-license=/path/to/license.lic"
    echo ""
    exit 0
fi

# -- early-exit: --update-license --------------------------------------------
if [ -n "${CMD_UPDATE_LIC}" ]; then
    [ -f "${CMD_UPDATE_LIC}" ] || die "File not found: ${CMD_UPDATE_LIC}"
    resolve_system_root
    cp "${CMD_UPDATE_LIC}" "${SYS_ROOT}/license.lic"
    ok "license.lic updated: ${SYS_ROOT}/license.lic"
    echo ""
    _PID_FILE="${SYS_ROOT}/logs/backend.pid"
    if [ -f "${_PID_FILE}" ]; then
        _PID="$(cat "${_PID_FILE}")"
        if kill -0 "${_PID}" 2>/dev/null; then
            info "Backend is running (PID=${_PID}). Restart to apply the new license:"
            info "  kill ${_PID}"
            info "  bash deploy.sh --background"
        else
            info "Backend is not running. Start with: bash deploy.sh --background"
        fi
    else
        info "Backend is not running. Start with: bash deploy.sh --background"
    fi
    echo ""
    exit 0
fi

resolve_system_root
echo ""
echo "Form System Kit Composer - Deploy"
echo "Recipe  : gui-selected-form-system"
echo "SysRoot : ${SYS_ROOT}"
echo ""

if [ "${WIZARD}" -eq 1 ]; then
    wizard_welcome
    wizard_configure
else
    configure_env
fi
configure_hiba_node
check_prerequisites
setup_venv
install_backend
run_kit_installs
build_frontend
setup_postgres
setup_database
start_backend
setup_nginx
send_hiba_dashboard_callback
show_license_notice

echo ""
echo "------------------------------------------------------"
echo "  === Deploy complete ==="
echo "------------------------------------------------------"
if [ "${BACKGROUND}" -eq 1 ]; then
    info "Backend : http://127.0.0.1:8000  (running in background)"
fi
info "Frontend: http://localhost  (served via nginx)"
if [ "${BACKGROUND}" -ne 1 ]; then
    info ""
    info "Start backend (foreground):"
    info "  cd ${SYS_ROOT}/backend && ${VENV}/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    info ""
    info "Or start in background:"
    info "  $0 --background"
fi
echo ""
echo "------------------------------------------------------"
echo "  WARNING: Production checklist"
echo "------------------------------------------------------"
info "1. Do NOT run as root. Create a system user:"
info "     sudo useradd -r -s /bin/false form-system"
info "2. Add TLS to nginx:"
info "     sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx"
info "3. DATABASE_URL, SECRET_KEY, and ADMIN_API_KEYS must be non-default values"
info "4. ENVIRONMENT=production disables the /docs endpoint"
info "5. Run: pip-audit  and  npm audit  (CVE scan)"
echo ""