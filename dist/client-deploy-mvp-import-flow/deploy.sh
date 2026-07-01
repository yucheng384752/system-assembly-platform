#!/usr/bin/env bash
# ================================================================
#  Form System Kit Composer - Server Deploy Script (Linux / macOS)
#  Recipe : mvp-import-flow
#  Built  : 2026-05-21 03:28
#  Kits   : platform-core-kit, tenant-auth-kit, station-data-link-kit, upload-validation-kit, import-pipeline-kit
#  DB     : postgresql
# ================================================================
#
#  Usage:
#    bash deploy.sh                            # auto-detect system/ next to this script
#    bash deploy.sh /opt/form-system           # specify system directory
#    bash deploy.sh /opt/form-system --background  # start in background

set -uo pipefail

die()  { echo "" >&2; echo "[ERROR] $*" >&2; echo "" >&2; exit 1; }
info() { echo "  $*"; }
ok()   { echo "  OK $*"; }

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
    echo ""
    if [ "${_MISSING}" -gt 0 ]; then
        die "${_MISSING} required tools missing. Install and retry."
    fi
    ok "All prerequisites present"
    echo ""
}

SCRIPT_DIR="$(cd "$(dirname "$0")" ; pwd)"
SYS_ROOT=""
BACKGROUND=0
for _arg in "$@"; do
    case "$_arg" in
        --background) BACKGROUND=1 ;;
        --*) die "Unknown option: $_arg" ;;
        *) SYS_ROOT="$_arg" ;;
    esac
done

if [ -z "${SYS_ROOT}" ]; then
    for _c in "$SCRIPT_DIR/system" "$SCRIPT_DIR/generated-system"; do
        if [ -d "$_c" ]; then SYS_ROOT="$_c"; break; fi
    done
fi
if [ -z "${SYS_ROOT}" ]; then
    die "Cannot find system dir. Usage: bash deploy.sh /path/to/system"
fi
if [ ! -d "${SYS_ROOT}" ]; then
    die "Directory not found: ${SYS_ROOT}"
fi
SYS_ROOT="$(cd "${SYS_ROOT}" ; pwd)"
if [ ! -f "${SYS_ROOT}/backend/requirements.txt" ]; then
    die "backend/requirements.txt not found. Verify path is the assembled system dir."
fi

echo ""
echo "Form System Kit Composer - Deploy"
echo "Recipe  : mvp-import-flow"
echo "SysRoot : ${SYS_ROOT}"
echo ""

check_prerequisites

echo "=== Installing dependencies ==="
pip3 install -r "${SYS_ROOT}/backend/requirements.txt"
ok "Backend dependencies installed"
if [ -f "${SYS_ROOT}/frontend/package.json" ]; then
    npm --prefix "${SYS_ROOT}/frontend" install
    ok "Frontend dependencies installed"
fi
echo ""

echo "=== Database migration ==="
if [ -f "${SYS_ROOT}/.env" ]; then
    set -a ; . "${SYS_ROOT}/.env" ; set +a
    info "Loaded ${SYS_ROOT}/.env"
fi
if [ -z "${DATABASE_URL:-}" ]; then
    die "DATABASE_URL not set. Create ${SYS_ROOT}/.env with DATABASE_URL=postgresql+asyncpg://..."
fi
(cd "${SYS_ROOT}/backend" ; python3 -m alembic upgrade head)
ok "Database migration complete"
echo ""

echo "=== Deploy complete ==="
if [ "${BACKGROUND}" -eq 1 ]; then
    mkdir -p "${SYS_ROOT}/logs"
    (cd "${SYS_ROOT}/backend" ; nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >"${SYS_ROOT}/logs/backend.log" 2>&1 &
    echo "$!" >"${SYS_ROOT}/logs/backend.pid")
    ok "Backend running in background on port 8000"
    info "Log: ${SYS_ROOT}/logs/backend.log"
    if [ -f "${SYS_ROOT}/frontend/package.json" ]; then
        info "Frontend: cd ${SYS_ROOT}/frontend && npm run dev"
    fi
else
    info "Start backend:"
    info "  cd ${SYS_ROOT}/backend && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    if [ -f "${SYS_ROOT}/frontend/package.json" ]; then
        info "Start frontend (separate terminal):"
        info "  cd ${SYS_ROOT}/frontend && npm run dev"
    fi
fi
echo ""
echo "------------------------------------------------------"
echo "  WARNING: Production checklist"
echo "------------------------------------------------------"
info "1. Do NOT run as root. Create a system user:"
info "     sudo useradd -r -s /bin/false form-system"
info "2. uvicorn has no TLS. Put a reverse proxy in front:"
info "     nginx + certbot (Let's Encrypt) or Caddy"
info "3. Verify DATABASE_URL password is not the default"
info "4. Set ENVIRONMENT=production to disable /docs"
info "5. Run: pip-audit  and  npm audit  (CVE check)"
echo ""
