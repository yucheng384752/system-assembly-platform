param(
    [string]$ProjectRoot      = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$RecipeName       = '',
    [string]$PackageName      = 'form-manager-system',
    [string]$OutputDir        = 'dist',
    [switch]$SkipZip,
    [string]$LicenseeName     = '',
    [string]$LicenseeEmail    = '',
    [int]$ExpiresAfterDays    = 0
)

$ErrorActionPreference = 'Stop'

function Assert-WizardFresh([string]$Root) {
    $wizardPy = Join-Path $Root "tools\install-wizard.py"
    $wizardExe = Join-Path $Root "tools\install-wizard.exe"
    if (Test-Path $wizardPy) {
        if (-not (Test-Path $wizardExe)) {
            throw "install-wizard.exe not found. Run tools\build-wizard-exe.ps1 before packaging."
        }
        $pyTime = (Get-Item $wizardPy).LastWriteTime
        $exeTime = (Get-Item $wizardExe).LastWriteTime
        if ($pyTime -gt $exeTime) {
            throw "install-wizard.py is newer than install-wizard.exe. Run tools\build-wizard-exe.ps1 before packaging."
        }
    }
}

Assert-WizardFresh $ProjectRoot

function Get-ProjectRelativePath([string]$Root, [string]$Path) {
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    if ($pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $pathFull.Substring($rootFull.Length + 1)
    }
    return $Path
}

# Find recipe ---------------------------------------------------------------
$assemblyDir = Join-Path $ProjectRoot 'assembly'
if ($RecipeName) {
    $recipePath = Join-Path $assemblyDir ($RecipeName + '.recipe.json')
} else {
    $recipePath = Get-ChildItem $assemblyDir -Filter '*.recipe.json' |
        Where-Object { $_.Name -notmatch '^(form-analysis-original|mvp-import-flow)' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $recipePath) {
        $recipePath = Get-ChildItem $assemblyDir -Filter '*.recipe.json' |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }
}
if (-not $recipePath -or -not (Test-Path $recipePath)) {
    throw 'Recipe not found. Export a recipe from the GUI to assembly/, or specify -RecipeName.'
}

$recipe  = [System.IO.File]::ReadAllText($recipePath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$rName   = $recipe.name
$rKits   = $recipe.enabledKits -join ', '
$rDb     = $recipe.database.engine
$dateStr = Get-Date -Format 'yyyy-MM-dd HH:mm'
$askAuth = (($recipe.enabledKits -contains 'tenant-auth-kit') -or ($recipe.featureFlags.AUTH_MODE -eq 'api_key')).ToString().ToLowerInvariant()
$askPdf = ([bool](($recipe.featureFlags.PDF_SERVER_URL) -or ($recipe.selectedSubfeatures.'upload-validation-kit' -contains 'pdf-to-csv-binding'))).ToString().ToLowerInvariant()
$askValidation = ($recipe.enabledKits -contains 'upload-validation-kit').ToString().ToLowerInvariant()

# Assemble generated-system from the selected recipe ------------------------
$sysRoot = Join-Path $ProjectRoot 'dist\generated-system'
Write-Host 'Resolving and assembling selected recipe...'
$resolvedPlanDir = Join-Path $ProjectRoot 'build\package-client-deploy'
New-Item -ItemType Directory -Force $resolvedPlanDir | Out-Null
$resolvedPlanPath = Join-Path $resolvedPlanDir ($rName + '.resolved-plan.json')
$recipeRelativePath = Get-ProjectRelativePath $ProjectRoot $recipePath
$resolvedPlanRelativePath = Get-ProjectRelativePath $ProjectRoot $resolvedPlanPath
& (Join-Path $ProjectRoot 'tools\resolve-recipe.ps1') `
    -ProjectRoot $ProjectRoot `
    -RecipePath $recipeRelativePath `
    -OutputPath $resolvedPlanRelativePath | Out-Null
& (Join-Path $ProjectRoot 'tools\assemble-system.ps1') `
    -ProjectRoot $ProjectRoot `
    -ResolvedPlanPath $resolvedPlanRelativePath `
    -OutputDirectory 'dist\generated-system' `
    -SkipFrontendBuild | Out-Null

# Validate generated-system -------------------------------------------------
if (-not (Test-Path (Join-Path $sysRoot 'backend\requirements.txt'))) {
    throw 'Generated system not found. Run tools\assemble-system.ps1 first.'
}
& (Join-Path $ProjectRoot 'tools\validate-generated-system.ps1') `
    -ProjectRoot $ProjectRoot `
    -GeneratedSystemDirectory 'dist\generated-system' | Out-Null

# Stage directory -----------------------------------------------------------
$pkgName  = if ($PackageName) { $PackageName } else { $rName }
$outRoot  = Join-Path $ProjectRoot $OutputDir
$stageDir = Join-Path $outRoot ('client-deploy-' + $pkgName)
$zipPath  = Join-Path $outRoot ($pkgName + '.zip')

if (Test-Path $stageDir) { Remove-Item $stageDir -Recurse -Force }
New-Item -ItemType Directory -Force $stageDir | Out-Null

# Copy system/ --------------------------------------------------------------
Write-Host 'Copying system/...'
Copy-Item $sysRoot (Join-Path $stageDir 'system') -Recurse -Force
# Remove Windows __pycache__ artifacts (incompatible with Linux Python)
Get-ChildItem (Join-Path $stageDir 'system') -Recurse -Filter '__pycache__' -Directory |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$stagedEnv = Join-Path $stageDir 'system\.env'
if (Test-Path $stagedEnv) {
    Remove-Item -LiteralPath $stagedEnv -Force
}
# Remove node_modules from staged frontend (pre-built dist/ is sufficient on server)
$stagedNodeModules = Join-Path $stageDir 'system\frontend\node_modules'
if (Test-Path $stagedNodeModules) {
    Remove-Item $stagedNodeModules -Recurse -Force
}

# Build deploy.sh -----------------------------------------------------------
Write-Host 'Generating deploy.sh...'
$bar = '=' * 64
$sq  = [char]39   # single-quote for bash (Let's Encrypt etc.)
$deployShContent = @'
#!/usr/bin/env bash
# __BAR__
#  Form System Kit Composer - Server Deploy Script (Linux / macOS)
#  Recipe : __RNAME__
#  Built  : __DATE__
#  Kits   : __RKITS__
#  DB     : __RDB__
# __BAR__
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

ASK_AUTH=__ASK_AUTH__
ASK_PDF=__ASK_PDF__
ASK_VALIDATION=__ASK_VALIDATION__
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
        info "Found deploy-init.env — loading pre-configured credentials..."
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

# ── Wizard helpers ──────────────────────────────────────────────────────────

wizard_welcome() {
    clear 2>/dev/null || true
    echo ""
    echo "================================================================"
    echo "  Form System 安裝精靈"
    echo "  Recipe : __RNAME__"
    echo "  Kits   : __RKITS__"
    echo "================================================================"
    echo ""
    echo "  此精靈將引導您完成："
    echo "    步驟 1／3  資料庫連線設定"
    echo "    步驟 2／3  管理者帳號設定"
    echo "    步驟 3／3  安全金鑰與確認"
    echo ""
    echo "  若已有 deploy-init.env，設定步驟將自動略過。"
    echo "  按 Ctrl+C 可隨時取消。"
    echo ""
    read -r -p "  按 Enter 繼續..." _dummy
    echo ""
}

_validate_nonempty() {
    local val="$1" label="$2"
    [ -n "$val" ] || { echo "  [!] ${label} 不得為空" >&2; return 1; }
}

_validate_port() {
    local val="$1"
    [[ "$val" =~ ^[0-9]+$ ]] && [ "$val" -ge 1 ] && [ "$val" -le 65535 ] || \
        { echo "  [!] 連接埠須為 1–65535 的整數" >&2; return 1; }
}

_validate_password() {
    local val="$1"
    [ ${#val} -ge 8 ] || { echo "  [!] 密碼長度至少 8 個字元" >&2; return 1; }
}

wizard_step1_db() {
    echo "──[ 步驟 1／3：資料庫連線 ]──────────────────────────────"
    echo ""
    echo "  支援 PostgreSQL（生產環境）。"
    echo "  若不設定 DATABASE_URL，系統將自動改用 SQLite（僅限本機測試）。"
    echo ""
    local _host _port _name _user _pass
    while true; do
        read -r -p "  資料庫主機位址 [localhost]: " _host
        _host="${_host:-localhost}"
        _validate_nonempty "$_host" "主機位址" && break
    done
    while true; do
        read -r -p "  資料庫連接埠 [5432]: " _port
        _port="${_port:-5432}"
        _validate_port "$_port" && break
    done
    while true; do
        read -r -p "  資料庫名稱 [form_system]: " _name
        _name="${_name:-form_system}"
        _validate_nonempty "$_name" "資料庫名稱" && break
    done
    while true; do
        read -r -p "  資料庫使用者 [form_system]: " _user
        _user="${_user:-form_system}"
        _validate_nonempty "$_user" "使用者名稱" && break
    done
    while true; do
        read -rsp "  資料庫密碼: " _pass; echo ""
        _validate_nonempty "$_pass" "密碼" && break
    done
    set_env_value DB_HOST     "$_host"
    set_env_value DB_PORT     "$_port"
    set_env_value DB_NAME     "$_name"
    set_env_value DB_USERNAME "$_user"
    set_env_value DB_PASSWORD "$_pass"
    set_env_value DATABASE_URL "postgresql+asyncpg://${_user}:${_pass}@${_host}:${_port}/${_name}"
    ok "資料庫設定完成"
    echo ""
}

wizard_step2_auth() {
    echo "──[ 步驟 2／3：管理者帳號 ]──────────────────────────────"
    echo ""
    echo "  設定系統初始 Manager 帳號，部署後可在後台新增或修改。"
    echo "  首次登入後系統將要求修改密碼。"
    echo ""
    local _user _pass _pass2
    while true; do
        read -r -p "  Manager 帳號名稱 [manager]: " _user
        _user="${_user:-manager}"
        _validate_nonempty "$_user" "帳號名稱" && break
    done
    while true; do
        read -rsp "  Manager 密碼（至少 8 碼）: " _pass; echo ""
        _validate_password "$_pass" || continue
        read -rsp "  確認密碼: " _pass2; echo ""
        [ "$_pass" = "$_pass2" ] && break
        echo "  [!] 兩次密碼不一致，請重新輸入" >&2
    done
    set_env_value BOOTSTRAP_MANAGER_ENABLED              "true"
    set_env_value BOOTSTRAP_MANAGER_TENANT_CODE          "default"
    set_env_value BOOTSTRAP_MANAGER_USERNAME             "$_user"
    set_env_value BOOTSTRAP_MANAGER_PASSWORD             "$_pass"
    set_env_value BOOTSTRAP_MANAGER_MUST_CHANGE_PASSWORD "true"
    ok "Manager 帳號設定完成"
    echo ""
}

wizard_step3_secrets() {
    echo "──[ 步驟 3／3：安全金鑰與確認 ]─────────────────────────"
    echo ""
    echo "  SECRET_KEY 用於 JWT / session 加密。"
    echo "  輸入 'g' 可自動產生隨機金鑰（推薦）。"
    echo ""
    prompt_secret SECRET_KEY "SECRET_KEY" 1
    set_env_value CORS_ORIGINS "http://localhost:5173,http://localhost:3000"
    ok "安全金鑰設定完成"
    echo ""
}

wizard_summary_confirm() {
    echo "──[ 安裝確認 ]────────────────────────────────────────────"
    echo ""
    echo "  資料庫    : $(get_env_value DB_HOST):$(get_env_value DB_PORT) / $(get_env_value DB_NAME)"
    echo "  DB 使用者 : $(get_env_value DB_USERNAME)"
    echo "  Manager   : $(get_env_value BOOTSTRAP_MANAGER_USERNAME)"
    echo "  CORS      : $(get_env_value CORS_ORIGINS)"
    echo "  密碼      : *** (已設定，不顯示)"
    echo ""
    local _confirm
    read -r -p "  確認設定正確，開始安裝？[y/N] " _confirm
    echo ""
    case "$_confirm" in
        y|Y|yes|YES) ok "開始安裝..." ;;
        *) die "安裝已取消。請重新執行 deploy.sh --wizard" ;;
    esac
}

wizard_configure() {
    if [ -f "${SCRIPT_DIR}/deploy-init.env" ]; then
        info "偵測到 deploy-init.env，載入預設設定..."
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

        # Stop a stale backend left over from a previous run, so port 8000 is
        # free before we start a new one. Only kill it if the PID is still
        # alive AND is actually our uvicorn process. Never touch an
        # unrelated PID that got reused.
        PID_FILE="${SYS_ROOT}/logs/backend.pid"
        if [ -f "${PID_FILE}" ]; then
            OLD_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
            if [ -n "${OLD_PID}" ] && kill -0 "${OLD_PID}" 2>/dev/null \
               && ps -p "${OLD_PID}" -o args= 2>/dev/null | grep -q "uvicorn app.main:app"; then
                info "Stopping previous backend (PID ${OLD_PID})..."
                kill "${OLD_PID}" 2>/dev/null || true
                for _ in 1 2 3 4 5 6 7 8 9 10; do
                    kill -0 "${OLD_PID}" 2>/dev/null || break
                    sleep 0.5
                done
                kill -0 "${OLD_PID}" 2>/dev/null && kill -9 "${OLD_PID}" 2>/dev/null || true
            fi
            rm -f "${PID_FILE}"
        fi

        # This VM is dedicated to running this system, so unlike the pidfile
        # check above (which never touches a PID it can't verify is our own
        # uvicorn), anything still squatting on port 8000 at this point is
        # assumed safe to kill outright.
        if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ':8000 '; then
            info "Port 8000 is occupied; this VM is dedicated to this system, freeing it..."
            OCCUPANT_PIDS="$(ss -tlnp 2>/dev/null | grep ':8000 ' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u)"
            for _p in ${OCCUPANT_PIDS}; do
                info "Killing PID ${_p} holding port 8000..."
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
                die "Port 8000 is still in use after attempting to free it. Check: sudo ss -tlnp | grep :8000"
            fi
        fi

        (
            cd "${SYS_ROOT}/backend"
            exec nohup "${VENV}/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 </dev/null >"${SYS_ROOT}/logs/backend.log" 2>&1
        ) &
        echo "$!" >"${PID_FILE}"
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
        info "nginx not found — installing..."
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
    # traversing into it — nginx would fail to stat the file (Permission denied),
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
        ok "nginx configured — frontend available at http://localhost"
    else
        info "nginx config test failed. Check: sudo nginx -t"
    fi
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
echo "Recipe  : __RNAME__"
echo "SysRoot : ${SYS_ROOT}"
echo ""

if [ "${WIZARD}" -eq 1 ]; then
    wizard_welcome
    wizard_configure
else
    configure_env
fi
check_prerequisites
setup_venv
install_backend
run_kit_installs
build_frontend
setup_postgres
setup_database
start_backend
setup_nginx
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
'@

$deployShContent = $deployShContent.Replace('__BAR__', $bar).Replace('__RNAME__', $rName).Replace('__DATE__', $dateStr).Replace('__RKITS__', $rKits).Replace('__RDB__', $rDb).Replace('__ASK_AUTH__', $askAuth).Replace('__ASK_PDF__', $askPdf).Replace('__ASK_VALIDATION__', $askValidation)
$deployShContent = $deployShContent -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'deploy.sh'),
    $deployShContent,
    (New-Object System.Text.UTF8Encoding $false)
)
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'deploy-offline.sh'),
    $deployShContent,
    (New-Object System.Text.UTF8Encoding $false)
)

$hibaShVars = @'
HIBA_NODE_ID="${HIBA_NODE_ID:-}"
HIBA_DASHBOARD_URL="${HIBA_DASHBOARD_URL:-}"
HIBA_DASHBOARD_TOKEN="${HIBA_DASHBOARD_TOKEN:-}"
HIBA_CALLBACK_ENABLED="${HIBA_CALLBACK_ENABLED:-true}"
'@ -replace "`r`n", "`n"

$hibaShFunctions = @'
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
    "recipe": "__RNAME__",
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
'@ -replace "`r`n", "`n"

$deployOnlineShContent = $deployShContent.Replace("ASK_VALIDATION=$askValidation", "ASK_VALIDATION=$askValidation`n$hibaShVars")
$rNamePyString = ($rName -replace '[\r\n]', '' -replace '\\', '\\' -replace '"', '\"')
$deployOnlineShContent = $deployOnlineShContent.Replace('# -- early-exit: --get-machine-id', ($hibaShFunctions.Replace('__RNAME__', $rNamePyString) + "`n# -- early-exit: --get-machine-id"))
$deployOnlineShContent = $deployOnlineShContent.Replace("fi`ncheck_prerequisites", "fi`nconfigure_hiba_node`ncheck_prerequisites")
if (-not $deployOnlineShContent.Contains("configure_hiba_node`ncheck_prerequisites")) {
    throw "HIBA inject failed: anchor 'fi\ncheck_prerequisites' not found in deploy-online.sh template."
}
$deployOnlineShContent = $deployOnlineShContent.Replace("setup_nginx`nshow_license_notice", "setup_nginx`nsend_hiba_dashboard_callback`nshow_license_notice")
if (-not $deployOnlineShContent.Contains("send_hiba_dashboard_callback`nshow_license_notice")) {
    throw "HIBA inject failed: anchor 'setup_nginx\nshow_license_notice' not found in deploy-online.sh template."
}
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'deploy-online.sh'),
    $deployOnlineShContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# Build deploy.ps1 (Windows orchestrator) -----------------------------------
Write-Host 'Generating deploy.ps1...'
$deployPs1Content = @'
#Requires -Version 5.1
<#
.SYNOPSIS
  Form System Kit Composer - Server Deploy Script (Windows)
  Recipe : __RNAME__
  Built  : __DATE__

.DESCRIPTION
  One-shot deploy: creates venv, installs deps, migrates DB, starts backend.

.EXAMPLE
  # Background mode (recommended for servers)
  .\deploy.ps1 -Background

  # Interactive (foreground, Ctrl+C to stop)
  .\deploy.ps1
#>
param(
    [string]$SysPath   = "",
    [switch]$Background,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- Locate system directory -------------------------------------------------
if ($SysPath) {
    $SysRoot = $SysPath
} else {
    foreach ($c in @("$ScriptDir\system", "$ScriptDir\generated-system")) {
        if (Test-Path "$c\backend\requirements.txt") { $SysRoot = $c; break }
    }
}
if (-not $SysRoot -or -not (Test-Path "$SysRoot\backend\requirements.txt")) {
    throw "Cannot locate system directory. Pass the path: .\deploy.ps1 C:\path\to\system"
}

$Scripts = "$SysRoot\scripts"
$Venv    = "$SysRoot\.venv"

Write-Host ""
Write-Host ("=" * 60)
Write-Host "  Form System Deploy - Windows"
Write-Host ("=" * 60)
Write-Host "  System : $SysRoot"
Write-Host ""

# --- Check and load .env into session environment ----------------------------
Write-Host "=== Checking .env ==="
$EnvFile = "$SysRoot\.env"
if (-not (Test-Path $EnvFile)) {
    $EnvExample = "$SysRoot\.env.example"
    if (Test-Path $EnvExample) {
        Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
        Write-Host ""
        Write-Host "  .env created from .env.example." -ForegroundColor Yellow
        Write-Host "  Edit it now (set SECRET_KEY, DATABASE_URL, ADMIN_API_KEYS), then re-run deploy.ps1." -ForegroundColor Yellow
        Write-Host "  File: $EnvFile" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    } else {
        throw "$EnvFile not found. Create system\.env from system\.env.example."
    }
}
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and $_ -notmatch '^\s*#') {
        $k = $Matches[1]; $v = $Matches[2]
        [System.Environment]::SetEnvironmentVariable($k, $v, 'Process')
    }
}
Write-Host "  OK .env loaded"
Write-Host "  Tip: No PostgreSQL? Use SQLite for local dev/testing:"
Write-Host "       DATABASE_URL=sqlite+aiosqlite:///./form_db.sqlite"
Write-Host ""

# --- Virtual environment -----------------------------------------------------
Write-Host "=== Setting up virtual environment ==="
python -m venv --clear "$Venv" | Out-Null
$Python = "$Venv\Scripts\python.exe"
& $Python -m pip install --quiet --upgrade pip
Write-Host "  OK venv at $Venv"
Write-Host ""

# --- Install backend dependencies --------------------------------------------
Write-Host "=== Installing backend dependencies ==="
& $Python -m pip install --quiet -r "$SysRoot\backend\requirements.txt"
Write-Host "  OK backend dependencies installed"

$KitInstallPlan = "$SysRoot\kitInstallPlan.json"
$KitInstallRunner = "$Scripts\run-kit-installs.ps1"
if (Test-Path $KitInstallPlan) {
    if (-not (Test-Path $KitInstallRunner)) {
        throw "Kit install runner not found: $KitInstallRunner"
    }
    Write-Host "=== Running kit installs ==="
    & powershell -ExecutionPolicy Bypass -File $KitInstallRunner -Root $SysRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Kit install runner failed with exit code $LASTEXITCODE."
    }
    Write-Host "  OK kit installs complete"
}

# --- Frontend (pre-built or build on-demand) ----------------------------------
if (-not $SkipFrontend) {
    $frontendDist = "$SysRoot\frontend\dist\index.html"
    $frontendPkg  = "$SysRoot\frontend\package.json"
    if (Test-Path $frontendDist) {
        Write-Host "  OK Frontend pre-built (dist\index.html present)"
    } elseif (Test-Path $frontendPkg) {
        Write-Host "=== Building frontend ==="
        Push-Location "$SysRoot\frontend"
        try {
            $npmArgs = @()
            $npmCache = Join-Path (Get-Location) ".npm-cache"
            if (Test-Path $npmCache) {
                $npmArgs += @("--cache", $npmCache, "--offline")
            }
            if (Test-Path "package-lock.json") {
                npm ci --silent @npmArgs
            } else {
                npm install --silent @npmArgs
            }
            npm run build
        } finally { Pop-Location }
        Write-Host "  OK frontend built"
    }
}
Write-Host ""

# --- Database migration ------------------------------------------------------
Write-Host "=== Database migration ==="
$alembicIni = "$SysRoot\backend\alembic.ini"
$bootstrap  = "$SysRoot\backend\app\core\generated_db_bootstrap.py"
if (Test-Path $alembicIni) {
    Push-Location "$SysRoot\backend"
    try { & $Python -m alembic upgrade head }
    finally { Pop-Location }
} elseif (Test-Path $bootstrap) {
    Push-Location "$SysRoot\backend"
    try { & $Python -m app.core.generated_db_bootstrap }
    finally { Pop-Location }
} else {
    Write-Warning "No migration tool found; skipping database setup."
}
Write-Host "  OK migration complete"
Write-Host ""

# --- Start backend -----------------------------------------------------------
Write-Host "=== Starting backend ==="
$RuntimePath = "$SysRoot\runtime"
$LogPath     = "$SysRoot\logs"
New-Item -ItemType Directory -Force $RuntimePath | Out-Null
New-Item -ItemType Directory -Force $LogPath     | Out-Null

if ($Background) {
    $backendPid = (Start-Process $Python -ArgumentList @(
        "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"
    ) -WorkingDirectory "$SysRoot\backend" `
      -WindowStyle Hidden `
      -RedirectStandardOutput "$LogPath\backend.out.log" `
      -RedirectStandardError  "$LogPath\backend.err.log" `
      -PassThru).Id
    [string]$backendPid | Set-Content -Encoding UTF8 "$RuntimePath\backend.pid"
    Write-Host "  OK backend PID=$backendPid  url=http://localhost:8000"
    Write-Host ""
    Write-Host "Backend is running in the background."
    Write-Host "  Health check : curl http://localhost:8000/healthz"
    Write-Host "  Logs         : $LogPath\backend.out.log"
    Write-Host "  Stop         : .\system\scripts\stop.ps1"
    Write-Host ""
    Write-Host "------------------------------------------------------"
    Write-Host "  WARNING: Production checklist"
    Write-Host "------------------------------------------------------"
    Write-Host "  1. Set DATABASE_URL and SECRET_KEY in system\.env"
    Write-Host "  2. AUTH_MODE=api_key is strongly recommended"
    Write-Host "  3. Use a reverse proxy (IIS / nginx / Caddy) with TLS"
    Write-Host "  4. ENVIRONMENT=production disables /docs endpoint"
} else {
    Write-Host "  Starting backend on http://localhost:8000 (Ctrl+C to stop)..."
    Push-Location "$SysRoot\backend"
    try { & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 }
    finally { Pop-Location }
}
'@

$deployPs1Content = $deployPs1Content.Replace('__RNAME__', $rName).Replace('__DATE__', $dateStr)
# Normalize to CRLF (Windows line endings) so PowerShell runs it cleanly on Windows
$deployPs1Content = $deployPs1Content -replace "`r`n", "`n" -replace "`n", "`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'deploy.ps1'),
    $deployPs1Content,
    (New-Object System.Text.UTF8Encoding $false)
)
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'deploy-offline.ps1'),
    $deployPs1Content,
    (New-Object System.Text.UTF8Encoding $false)
)

$hibaPs1Params = @'
,
    [string]$HibaNodeId = "",
    [string]$HibaDashboardUrl = "",
    [string]$HibaDashboardToken = "",
    [bool]$HibaCallbackEnabled = $true
'@

$hibaPs1Functions = @'

function Protect-EnvFile([string]$Path) {
    try {
        if (-not (Test-Path -LiteralPath $Path)) { return }
        $acl = Get-Acl -LiteralPath $Path
        $acl.SetAccessRuleProtection($true, $false)
        $current = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        foreach ($identity in @($current, "BUILTIN\Administrators", "NT AUTHORITY\SYSTEM")) {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                $identity,
                "FullControl",
                "Allow"
            )
            $acl.AddAccessRule($rule)
        }
        Set-Acl -LiteralPath $Path -AclObject $acl
    } catch {
        Write-Warning "Could not restrict $Path ACL: $($_.Exception.Message)"
    }
}

function Set-EnvFileValue([string]$Path, [string]$Key, [string]$Value) {
    $lines = @()
    if (Test-Path $Path) { $lines = @(Get-Content -LiteralPath $Path) }
    $escaped = $Value -replace '\\', '\\'
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^$([regex]::Escape($Key))=") {
            $found = $true
            "$Key=$escaped"
        } else {
            $line
        }
    }
    if (-not $found) { $updated += "$Key=$escaped" }
    Set-Content -LiteralPath $Path -Value $updated -Encoding UTF8
    Protect-EnvFile $Path
    [System.Environment]::SetEnvironmentVariable($Key, $Value, 'Process')
}

function Configure-HibaNode {
    param([string]$EnvFile)
    Write-Host "=== HIBA Node ==="
    if (-not $script:HibaNodeId) {
        $machineGuid = ""
        try { $machineGuid = (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name MachineGuid).MachineGuid } catch {}
        $script:HibaNodeId = if ($machineGuid) { $machineGuid } else { $env:COMPUTERNAME }
    }
    if (-not $script:HibaDashboardUrl) {
        $script:HibaDashboardUrl = [System.Environment]::GetEnvironmentVariable("HIBA_DASHBOARD_URL", 'Process')
    }
    if (-not $script:HibaDashboardUrl) {
        throw "HIBA_DASHBOARD_URL not set. Pass -HibaDashboardUrl or set it in system\.env."
    }
    Set-EnvFileValue $EnvFile "HIBA_NODE_ID" $script:HibaNodeId
    Set-EnvFileValue $EnvFile "HIBA_DASHBOARD_URL" $script:HibaDashboardUrl
    Set-EnvFileValue $EnvFile "HIBA_DASHBOARD_TOKEN" $script:HibaDashboardToken
    Set-EnvFileValue $EnvFile "HIBA_CALLBACK_ENABLED" ([string]$script:HibaCallbackEnabled).ToLowerInvariant()
    Write-Host "  OK HIBA node configured: $script:HibaNodeId"
    Write-Host ""
}

function Send-HibaDashboardCallback {
    if (-not $script:HibaCallbackEnabled) { return }
    if (-not $script:HibaDashboardUrl) { return }
    Write-Host "=== HIBA Dashboard Callback ==="
    try {
        $uri = $script:HibaDashboardUrl.TrimEnd("/") + "/api/hiba/nodes/register"
        $body = @{
            nodeId = $script:HibaNodeId
            recipe = "__RNAME__"
            status = "deployed"
            hostname = $env:COMPUTERNAME
            systemRoot = $SysRoot
            timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        } | ConvertTo-Json -Depth 4
        $headers = @{ "Content-Type" = "application/json" }
        if ($script:HibaDashboardToken) { $headers["Authorization"] = "Bearer $script:HibaDashboardToken" }
        $resp = Invoke-WebRequest -Uri $uri -Method Post -Headers $headers -Body $body -UseBasicParsing -TimeoutSec 15
        Write-Host "  OK dashboard callback HTTP $($resp.StatusCode)"
    } catch {
        Write-Warning "dashboard callback failed: $($_.Exception.Message)"
    }
    Write-Host ""
}
'@

$deployOnlinePs1Content = $deployPs1Content.Replace("[switch]`$SkipFrontend", "[switch]`$SkipFrontend$hibaPs1Params")
$normalizedHibaPs1Functions = $hibaPs1Functions.Replace('__RNAME__', $rName) -replace "`r`n", "`n" -replace "`n", "`r`n"
$deployOnlinePs1Content = $deployOnlinePs1Content.Replace('# --- Check and load .env into session environment', ($normalizedHibaPs1Functions + "`r`n# --- Check and load .env into session environment"))
$deployOnlinePs1Content = $deployOnlinePs1Content.Replace('Write-Host "  OK .env loaded"', 'Write-Host "  OK .env loaded"' + "`r`n" + 'Configure-HibaNode $EnvFile')
$deployOnlinePs1Content = $deployOnlinePs1Content.Replace('Write-Host "  OK backend PID=$backendPid  url=http://localhost:8000"', 'Write-Host "  OK backend PID=$backendPid  url=http://localhost:8000"' + "`r`n" + '    Send-HibaDashboardCallback')
$deployOnlinePs1Content = $deployOnlinePs1Content.Replace('try { & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 }', 'try {' + "`r`n" + '        Send-HibaDashboardCallback' + "`r`n" + '        & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000' + "`r`n" + '    }')
if (-not (
    $deployOnlinePs1Content.Contains('Write-Host "  OK backend PID=$backendPid  url=http://localhost:8000"' + "`r`n" + '    Send-HibaDashboardCallback') -and
    $deployOnlinePs1Content.Contains('try {' + "`r`n" + '        Send-HibaDashboardCallback' + "`r`n" + '        & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000')
)) {
    throw "HIBA inject failed: Send-HibaDashboardCallback not found in deploy-online.ps1 template (anchor may have changed)."
}
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'deploy-online.ps1'),
    $deployOnlinePs1Content,
    (New-Object System.Text.UTF8Encoding $false)
)

# Build README.md -----------------------------------------------------------
Write-Host 'Generating README.md...'
$tick3 = '```'
$tick1 = '`'
$R = [System.Collections.Generic.List[string]]::new()
$R.Add('# Form System - Client Deploy Package')
$R.Add('')
$R.Add('| Field   | Value |')
$R.Add('|---------|-------|')
$R.Add('| Recipe  | ' + $tick1 + $rName + $tick1 + ' |')
$R.Add('| Built   | ' + $dateStr + ' |')
$R.Add('| DB      | ' + $rDb + ' |')
$R.Add('| Kits    | ' + $rKits + ' |')
$R.Add('')
$R.Add('## Package contents')
$R.Add('')
$R.Add($tick3)
$R.Add('client-deploy-' + $pkgName + '/')
$R.Add('|-- system/              <- Assembled system (backend + pre-built frontend + scripts)')
$R.Add('|-- docker/              <- Dockerfiles + nginx config (Docker mode)')
$R.Add('|   |-- backend.Dockerfile')
$R.Add('|   |-- frontend.Dockerfile')
$R.Add('|   +-- nginx.conf')
$R.Add('|-- docker-compose.yml  <- Docker Compose (one-command deploy)')
$R.Add('|-- .env.docker         <- Environment template for Docker')
$R.Add('|-- nginx.conf          <- nginx config for direct nginx setup (no Docker)')
$R.Add('|-- deploy.sh           <- Traditional deploy script (Linux / macOS)')
$R.Add('|-- recipe.json         <- Assembly recipe')
$R.Add($tick3)
$R.Add('')
$R.Add('## Deployment (Ubuntu 22.04 / macOS)')
$R.Add('')
$R.Add('### 1. Extract ZIP')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('unzip ' + $pkgName + '.zip')
$R.Add('cd client-deploy-' + $pkgName)
$R.Add($tick3)
$R.Add('')
$R.Add('### 2. Install')
$R.Add('')
$R.Add('#### No Python yet? Run bootstrap first')
$R.Add('')
$R.Add('On a fresh VM without Python 3, run the bootstrap script — it installs Python 3 + pip (online via apt/dnf/yum/winget, or offline from ' + $tick1 + 'installers/' + $tick1 + '), then launches the wizard:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash bootstrap.sh          # Linux / macOS')
$R.Add($tick3)
$R.Add('')
$R.Add($tick3 + 'powershell')
$R.Add('.\bootstrap.ps1            # Windows')
$R.Add($tick3)
$R.Add('')
$R.Add('> Offline machines: drop the Python installer into ' + $tick1 + 'installers/' + $tick1 + ' before transfer (see ' + $tick1 + 'installers/README.txt' + $tick1 + '). ' + $tick1 + 'prepare-offline.ps1' + $tick1 + ' auto-bundles the Windows installer.')
$R.Add('')
$R.Add('#### Option A — Web Install Wizard (recommended, Python already installed)')
$R.Add('')
$R.Add('Interactive browser-based wizard. No extra dependencies — only Python 3 required.')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('python3 install-wizard.py')
$R.Add($tick3)
$R.Add('')
$R.Add('Opens ' + $tick1 + 'http://localhost:9981/' + $tick1 + ' automatically. Guides you through database, manager account, security keys, and runs the install pipeline with live progress.')
$R.Add('')
$R.Add('Windows:')
$R.Add('')
$R.Add($tick3 + 'powershell')
$R.Add('python install-wizard.py')
$R.Add($tick3)
$R.Add('')
$R.Add('#### Option B — CLI Wizard (SSH / headless servers)')
$R.Add('')
$R.Add('Step-by-step text prompts for database, manager account, and secret key.')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash deploy.sh --wizard')
$R.Add($tick3)
$R.Add('')
$R.Add('To start the backend in the background after install:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash deploy.sh --wizard --background')
$R.Add($tick3)
$R.Add('')
$R.Add('#### Option C — Manual config (advanced)')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('cp system/.env.example system/.env')
$R.Add('nano system/.env')
$R.Add($tick3)
$R.Add('')
$R.Add('Required fields:')
$R.Add('')
$R.Add($tick3)
$R.Add('DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/form_system')
$R.Add('SECRET_KEY=<random-64-char-string>')
$R.Add('CORS_ORIGINS=http://localhost:5173,http://localhost:3000')
$R.Add('BOOTSTRAP_MANAGER_ENABLED=true')
$R.Add('BOOTSTRAP_MANAGER_USERNAME=manager')
$R.Add('BOOTSTRAP_MANAGER_PASSWORD=<min-8-chars>')
$R.Add($tick3)
$R.Add('')
$R.Add('Generate a strong SECRET_KEY:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('python3 -c "import secrets; print(secrets.token_urlsafe(48))"')
$R.Add($tick3)
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash deploy.sh')
$R.Add($tick3)
$R.Add('')
$R.Add('The script automatically:')
$R.Add('')
$R.Add('1. Configures or validates ' + $tick1 + '.env' + $tick1 + ' (interactive mode can create/update it)')
$R.Add('2. Checks prerequisites (python3, pip3, node, npm)')
$R.Add('3. Creates an isolated Python virtual environment at ' + $tick1 + 'system/.venv' + $tick1)
$R.Add('4. Installs backend dependencies via ' + $tick1 + 'pip' + $tick1 + ' into the venv')
$R.Add('5. Builds the frontend (' + $tick1 + 'npm ci' + $tick1 + ' when package-lock.json exists, then ' + $tick1 + 'npm run build' + $tick1 + ')')
$R.Add('6. Runs database migrations (' + $tick1 + 'alembic upgrade head' + $tick1 + ' or ' + $tick1 + 'generated_db_bootstrap.py' + $tick1 + ')')
$R.Add('')
$R.Add('### 4. Start the backend')
$R.Add('')
$R.Add('**Option A - foreground (for testing):**')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('cd system/backend')
$R.Add('../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000')
$R.Add($tick3)
$R.Add('')
$R.Add('**Option B - background (recommended for servers):**')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash deploy.sh --background')
$R.Add('# Log : system/logs/backend.log')
$R.Add('# Stop: kill $(cat system/logs/backend.pid)')
$R.Add($tick3)
$R.Add('')
$R.Add('### 5. Serve the frontend')
$R.Add('')
$R.Add('Frontend static files are **pre-built** and included at ' + $tick1 + 'system/frontend/dist/' + $tick1 + '. Node.js is not required on the server.')
$R.Add('')
$R.Add('A ready-to-use nginx config is provided at ' + $tick1 + 'nginx.conf' + $tick1 + '. Edit the ' + $tick1 + 'root' + $tick1 + ' path, then:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('sudo cp nginx.conf /etc/nginx/sites-available/form-system')
$R.Add('sudo ln -s /etc/nginx/sites-available/form-system /etc/nginx/sites-enabled/')
$R.Add('sudo nginx -t && sudo systemctl reload nginx')
$R.Add($tick3)
$R.Add('')
$R.Add('Or configure manually to serve via nginx as a reverse proxy:')
$R.Add('')
$R.Add($tick3 + 'nginx')
$R.Add('server {')
$R.Add('    listen 80;')
$R.Add('    server_name your-domain.com;')
$R.Add('    root /path/to/client-deploy-' + $rName + '/system/frontend/dist;')
$R.Add('    index index.html;')
$R.Add('')
$R.Add('    location / {')
$R.Add('        try_files $uri $uri/ /index.html;')
$R.Add('    }')
$R.Add('    location /api/ {')
$R.Add('        proxy_pass http://127.0.0.1:8000;')
$R.Add('        proxy_set_header Host $host;')
$R.Add('        proxy_set_header X-Real-IP $remote_addr;')
$R.Add('    }')
$R.Add('}')
$R.Add($tick3)
$R.Add('')
$R.Add('> Dev only (not for production): ' + $tick1 + 'cd system/frontend && npm run dev' + $tick1)
$R.Add('')
$R.Add('## License management')
$R.Add('')
$R.Add('A signed ' + $tick1 + 'license.lic' + $tick1 + ' is included in this package.')
$R.Add('')
$R.Add('### Get machine fingerprint (for machine-bound license)')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash deploy.sh --get-machine-id')
$R.Add($tick3)
$R.Add('')
$R.Add('Share the printed Fingerprint with your vendor. They will re-sign the license for your machine.')
$R.Add('')
$R.Add('### Apply a new license (without reinstalling)')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash deploy.sh --update-license=/path/to/new-license.lic')
$R.Add($tick3)
$R.Add('')
$R.Add('The script copies the file to ' + $tick1 + 'system/license.lic' + $tick1 + ' and prints restart instructions if the backend is running.')
$R.Add('')
$R.Add('## Troubleshooting')
$R.Add('')
$R.Add('### Manager account won' + $sq + 't log in (even with the username/password you set in the installer)')
$R.Add('')
$R.Add('The installer writes ' + $tick1 + 'BOOTSTRAP_MANAGER_USERNAME' + $tick1 + '/' + $tick1 + 'BOOTSTRAP_MANAGER_PASSWORD' + $tick1 + ' into ' + $tick1 + '.env' + $tick1 + ', but the backend only uses them to *create* the manager account on ' + $sq + 'first ever' + $sq + ' startup. If a manager account with that username already exists (e.g. from an earlier install attempt against the same database), changing ' + $tick1 + '.env' + $tick1 + ' afterwards has no effect: the stored password is never overwritten.')
$R.Add('')
$R.Add('Reset it directly with the break-glass script:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('cd system/backend')
$R.Add('../.venv/bin/python scripts/reset-manager-password.py --username manager')
$R.Add('# or non-interactively:')
$R.Add('../.venv/bin/python scripts/reset-manager-password.py --username manager --new-password ' + $sq + 'NewP@ssw0rd' + $sq)
$R.Add($tick3)
$R.Add('')
$R.Add('To list existing manager/admin accounts without changing anything:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('../.venv/bin/python scripts/reset-manager-password.py --list')
$R.Add($tick3)
$R.Add('')
$R.Add('The script reads ' + $tick1 + 'DATABASE_URL' + $tick1 + ' from ' + $tick1 + '.env' + $tick1 + ' and connects with the same async driver the backend uses, so there is no separate DB client to set up. New passwords must be at least 8 characters, and the account is flagged to prompt a password change on next login.')
$R.Add('')
$R.Add('## Production security checklist')
$R.Add('')
$R.Add('- [ ] Do NOT run as root: ' + $tick1 + 'sudo useradd -r -s /bin/false form-system' + $tick1)
$R.Add('- [ ] Set up nginx + TLS (Let' + $sq + 's Encrypt / Caddy)')
$R.Add('- [ ] ' + $tick1 + 'AUTH_MODE=api_key' + $tick1 + ' is set (required in production)')
$R.Add('- [ ] ' + $tick1 + 'SECRET_KEY' + $tick1 + ' is a strong random value (not the default)')
$R.Add('- [ ] ' + $tick1 + 'DATABASE_URL' + $tick1 + ' uses a strong password (not the default)')
$R.Add('- [ ] ' + $tick1 + 'ENVIRONMENT=production' + $tick1 + ' is set (disables /docs)')
$R.Add('- [ ] Run ' + $tick1 + 'pip-audit' + $tick1 + ' and ' + $tick1 + 'npm audit' + $tick1)
$R.Add('- [ ] Rotate SECRET_KEY and API keys periodically')
$R.Add('')
$R.Add('## Docker Compose (quick start)')
$R.Add('')
$R.Add('No manual PostgreSQL or Python installation required.')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('# 1. Configure environment')
$R.Add('cp .env.docker .env')
$R.Add('nano .env   # set DB_PASSWORD, SECRET_KEY, ADMIN_API_KEYS')
$R.Add('')
$R.Add('# 2. Start all services (db + backend + frontend/nginx)')
$R.Add('docker compose up -d')
$R.Add('')
$R.Add('# 3. Open in browser')
$R.Add('# http://localhost        (frontend via nginx)')
$R.Add('# http://localhost:8000   (backend API)')
$R.Add($tick3)
$R.Add('')
$R.Add('Stop services:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('docker compose down          # stop (keep database volume)')
$R.Add('docker compose down -v       # stop and delete database')
$R.Add('docker compose logs -f       # stream live logs')
$R.Add($tick3)

$readmeContent = $R -join "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'README.md'),
    $readmeContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# Generate Docker Compose files -----------------------------------------------
Write-Host 'Generating Docker Compose files...'
New-Item -ItemType Directory -Force (Join-Path $stageDir 'docker') | Out-Null

$dockerComposeContent = @'
# Generated by Form System Kit Composer - Recipe: __RNAME__
#
# Quick start:
#   cp .env.docker .env && nano .env   # set DB_PASSWORD, SECRET_KEY, ADMIN_API_KEYS
#   docker compose up -d
#   open http://localhost

services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME:-form_db}
      POSTGRES_USER: ${DB_USER:-form_user}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${DB_USER:-form_user}"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    restart: unless-stopped
    environment:
      DATABASE_URL: "postgresql+asyncpg://${DB_USER:-form_user}:${DB_PASSWORD:-changeme}@db:5432/${DB_NAME:-form_db}"
      SECRET_KEY: ${SECRET_KEY:-changeme-replace-before-production}
      CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost}
      AUTH_MODE: ${AUTH_MODE:-api_key}
      ADMIN_API_KEYS: ${ADMIN_API_KEYS:-changeme-replace-before-production}
      ENVIRONMENT: ${ENVIRONMENT:-production}
      BOOTSTRAP_MANAGER_ENABLED: ${BOOTSTRAP_MANAGER_ENABLED:-false}
      BOOTSTRAP_MANAGER_USERNAME: ${BOOTSTRAP_MANAGER_USERNAME:-}
      BOOTSTRAP_MANAGER_PASSWORD: ${BOOTSTRAP_MANAGER_PASSWORD:-}
      BOOTSTRAP_MANAGER_TENANT_CODE: ${BOOTSTRAP_MANAGER_TENANT_CODE:-}
      USE_GENERIC_SCHEMA: ${USE_GENERIC_SCHEMA:-false}
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build:
      context: .
      dockerfile: docker/frontend.Dockerfile
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  db-data:
'@
$dockerComposeContent = $dockerComposeContent.Replace('__RNAME__', $rName) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'docker-compose.yml'),
    $dockerComposeContent,
    (New-Object System.Text.UTF8Encoding $false)
)

$backendDockerfileContent = @'
FROM python:3.11-slim
WORKDIR /app
COPY system/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY system/backend/ .
COPY system/kits/ ./kits/
COPY system/db-bootstrap-plan.json ./db-bootstrap-plan.json
COPY license.lic /app/license.lic
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
'@
$backendDockerfileContent = $backendDockerfileContent -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'docker\backend.Dockerfile'),
    $backendDockerfileContent,
    (New-Object System.Text.UTF8Encoding $false)
)

$frontendDockerfileContent = @'
FROM node:20-slim AS builder
WORKDIR /app
COPY system/frontend/ .
RUN NPM_CACHE_ARGS=""; \
    if [ -d .npm-cache ]; then NPM_CACHE_ARGS="--cache .npm-cache --offline"; fi; \
    if [ -f package-lock.json ]; then npm ci --silent $NPM_CACHE_ARGS; else npm install --silent $NPM_CACHE_ARGS; fi; \
    npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
'@
$frontendDockerfileContent = $frontendDockerfileContent -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'docker\frontend.Dockerfile'),
    $frontendDockerfileContent,
    (New-Object System.Text.UTF8Encoding $false)
)

$nginxConfContent = @'
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/healthz {
        proxy_pass http://backend:8000/healthz;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
'@
$nginxConfContent = $nginxConfContent -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'docker\nginx.conf'),
    $nginxConfContent,
    (New-Object System.Text.UTF8Encoding $false)
)

$envDockerContent = @'
# Docker Compose environment — copy to .env and edit before running docker compose up
DB_NAME=form_db
DB_USER=form_user
DB_PASSWORD=changeme

# Generate SECRET_KEY: python3 -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=changeme

CORS_ORIGINS=http://localhost
AUTH_MODE=api_key
ADMIN_API_KEYS=changeme
ENVIRONMENT=production
'@
$envDockerContent = $envDockerContent -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir '.env.docker'),
    $envDockerContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# Generate standalone nginx.conf (for direct nginx without Docker) --------------
Write-Host 'Generating nginx.conf...'
$nginxStandaloneContent = @'
# nginx reverse proxy config for client-deploy-__RNAME__
# 1. Edit the "root" path below to the absolute deploy directory
# 2. sudo cp nginx.conf /etc/nginx/sites-available/form-system
# 3. sudo ln -s /etc/nginx/sites-available/form-system /etc/nginx/sites-enabled/
# 4. sudo nginx -t && sudo systemctl reload nginx
#
# IMPORTANT: if you extract the deploy package under a user's home directory
# (e.g. /home/<user>/...) instead of /opt, the nginx worker (www-data) will
# likely get "Permission denied" traversing into it (home dirs default to
# 750/770). Either keep the deploy under /opt as shown below, or copy
# system/frontend/dist to a world-readable path (e.g. /var/www/form-system)
# and point "root" there instead.

server {
    listen 80;
    server_name _;

    # Update to the absolute path where you extracted the deploy package
    root /opt/form-system/client-deploy-__PKGNAME__/system/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
'@
$nginxStandaloneContent = $nginxStandaloneContent.Replace('__PKGNAME__', $pkgName).Replace('__RNAME__', $rName) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'nginx.conf'),
    $nginxStandaloneContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# Copy recipe.json ----------------------------------------------------------
Copy-Item $recipePath (Join-Path $stageDir 'recipe.json') -Force

# Copy install-wizard.py (local web installer) ------------------------------
$wizardSrc = Join-Path $PSScriptRoot 'install-wizard.py'
if (Test-Path $wizardSrc) {
    Write-Host 'Copying install-wizard.py...'
    Copy-Item $wizardSrc (Join-Path $stageDir 'install-wizard.py') -Force
} else {
    Write-Host 'SKIP install-wizard.py (not found at tools\install-wizard.py)'
}

# Copy install-wizard.exe if pre-built (run tools\build-wizard-exe.ps1 once to generate) ------
$wizardExe = Join-Path $PSScriptRoot 'install-wizard.exe'
if (Test-Path $wizardExe) {
    Write-Host 'Copying install-wizard.exe...'
    Copy-Item $wizardExe (Join-Path $stageDir 'install-wizard.exe') -Force
} else {
    Write-Host 'SKIP install-wizard.exe (run tools\build-wizard-exe.ps1 to pre-build)'
}

# Generate startup scripts (Phase 2) ----------------------------------------
Write-Host 'Generating startup scripts...'
$startShContent = @'
#!/usr/bin/env bash
# Start __PKGNAME__
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
'@
$startShContent = $startShContent.Replace('__PKGNAME__', $pkgName) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'start-form-manager.sh'),
    $startShContent,
    (New-Object System.Text.UTF8Encoding $false)
)

$startPs1Content = @'
#Requires -Version 5.1
# Start __PKGNAME__
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ((Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path "$ScriptDir\docker-compose.yml")) {
    docker compose -f "$ScriptDir\docker-compose.yml" up -d
    Write-Host "  Services started.  Frontend: http://localhost"
    exit 0
}

$SysRoot = "$ScriptDir\system"
if (-not (Test-Path $SysRoot)) { throw "system/ not found — run deploy.ps1 first" }
$Python = "$SysRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "venv not found — run deploy.ps1 first" }
New-Item -ItemType Directory -Force "$SysRoot\logs","$SysRoot\runtime" | Out-Null
$proc = Start-Process $Python `
    -ArgumentList @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000") `
    -WorkingDirectory "$SysRoot\backend" -WindowStyle Hidden `
    -RedirectStandardOutput "$SysRoot\logs\backend.out.log" `
    -RedirectStandardError  "$SysRoot\logs\backend.err.log" `
    -PassThru
[string]$proc.Id | Set-Content -Encoding UTF8 "$SysRoot\runtime\backend.pid"
Write-Host "  Backend started (PID=$($proc.Id)).  API: http://127.0.0.1:8000"
Write-Host "  Frontend: http://localhost  (requires nginx)"
'@
$startPs1Content = $startPs1Content.Replace('__PKGNAME__', $pkgName) -replace "`r`n", "`n" -replace "`n", "`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'start-form-manager.ps1'),
    $startPs1Content,
    (New-Object System.Text.UTF8Encoding $false)
)

$startupCmd = [ordered]@{
    systemName = $pkgName
    mode       = 'auto'
    commands   = [ordered]@{
        windows = '.\start-form-manager.ps1'
        linux   = './start-form-manager.sh'
    }
    urls       = [ordered]@{
        frontend      = 'http://localhost'
        backendHealth = 'http://localhost:8000/healthz'
    }
}
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'startup-command.json'),
    (($startupCmd | ConvertTo-Json -Depth 4) -replace "`r`n", "`n"),
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host '  OK start-form-manager.sh / .ps1 / startup-command.json'

# Generate bootstrap scripts (ensure Python 3 before the wizard) ------------
Write-Host 'Generating bootstrap scripts...'
$bootstrapSh = @'
#!/usr/bin/env bash
# __PKGNAME__ — bootstrap: ensure Python 3 + pip, then launch the install wizard.
# Run this FIRST on a fresh VM that may not have Python installed.
#   bash bootstrap.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" ; pwd)"

info() { echo "  $*"; }
die()  { echo "" >&2; echo "[ERROR] $*" >&2; exit 1; }

install_python() {
    # 1) Offline: install from bundled installers/ (drop .deb/.rpm there before transfer)
    if compgen -G "${SCRIPT_DIR}/installers/*.deb" >/dev/null 2>&1; then
        info "Installing Python from bundled .deb..."
        sudo dpkg -i "${SCRIPT_DIR}/installers/"*.deb || sudo apt-get install -f -y
        return
    fi
    if compgen -G "${SCRIPT_DIR}/installers/*.rpm" >/dev/null 2>&1; then
        info "Installing Python from bundled .rpm..."
        sudo rpm -Uvh --replacepkgs "${SCRIPT_DIR}/installers/"*.rpm || sudo yum localinstall -y "${SCRIPT_DIR}/installers/"*.rpm
        return
    fi
    # 2) Online: OS package manager
    if command -v apt-get >/dev/null 2>&1; then
        info "Installing Python via apt-get..."
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
    elif command -v dnf >/dev/null 2>&1; then
        info "Installing Python via dnf..."
        sudo dnf install -y python3 python3-pip
    elif command -v yum >/dev/null 2>&1; then
        info "Installing Python via yum..."
        sudo yum install -y python3 python3-pip
    else
        die "No bundled installer in installers/ and no package manager found. Install Python 3.11+ manually: https://www.python.org/downloads/"
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    info "Python 3 not found."
    install_python
    command -v python3 >/dev/null 2>&1 || die "Python install did not succeed. Install Python 3.11+ manually."
fi
info "Python: $(python3 --version 2>&1)"

if ! python3 -m pip --version >/dev/null 2>&1; then
    info "pip not found — bootstrapping with ensurepip..."
    python3 -m ensurepip --upgrade || die "Could not install pip. Install python3-pip manually."
fi
info "pip: $(python3 -m pip --version 2>&1)"

echo ""
info "Launching install wizard..."
exec python3 "${SCRIPT_DIR}/install-wizard.py"
'@
$bootstrapSh = $bootstrapSh.Replace('__PKGNAME__', $pkgName) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'bootstrap.sh'),
    $bootstrapSh,
    (New-Object System.Text.UTF8Encoding $false)
)

$bootstrapPs1 = @'
#Requires -Version 5.1
# __PKGNAME__ — bootstrap: ensure Python 3 + pip, then launch the install wizard.
# Run this FIRST on a fresh VM that may not have Python installed.
#   .\bootstrap.ps1
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-Python { [bool](Get-Command python -ErrorAction SilentlyContinue) }

function Install-Python {
    # 1) Offline: bundled installer in installers\ (drop .exe/.msi there before transfer)
    $inst = Get-ChildItem -Path "$ScriptDir\installers" -Include *.exe,*.msi -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($inst) {
        Write-Host "  Installing Python from bundled $($inst.Name)..."
        if ($inst.Extension -eq ".msi") {
            Start-Process msiexec.exe -ArgumentList "/i `"$($inst.FullName)`" /quiet InstallAllUsers=1 PrependPath=1" -Wait
        } else {
            Start-Process $inst.FullName -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
        }
        return
    }
    # 2) Online: winget
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  Installing Python via winget..."
        winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        return
    }
    throw "No bundled installer in installers\ and winget unavailable. Install Python 3.11+ from https://www.python.org/downloads/"
}

if (-not (Test-Python)) {
    Write-Host "  Python not found."
    Install-Python
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    if (-not (Test-Python)) {
        throw "Python installed but not yet on PATH. Close and reopen PowerShell, then re-run bootstrap.ps1."
    }
}
Write-Host "  Python: $(python --version 2>&1)"

python -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  pip not found — bootstrapping with ensurepip..."
    python -m ensurepip --upgrade
}

Write-Host ""
Write-Host "  Launching install wizard..."
python "$ScriptDir\install-wizard.py"
'@
$bootstrapPs1 = $bootstrapPs1.Replace('__PKGNAME__', $pkgName) -replace "`r`n", "`n" -replace "`n", "`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'bootstrap.ps1'),
    $bootstrapPs1,
    (New-Object System.Text.UTF8Encoding $false)
)

# installers/ drop-in folder for offline Python (populated by prepare-offline.ps1) ---
New-Item -ItemType Directory -Force (Join-Path $stageDir 'installers') | Out-Null
$installersReadme = @'
Offline Python installers
=========================

If the target machine has NO internet AND no Python 3, drop the matching
Python installer here BEFORE transferring this package. bootstrap.sh /
bootstrap.ps1 will detect and install from this folder automatically.

  Windows       : python-3.11.x-amd64.exe (or .msi)
                  https://www.python.org/downloads/windows/
  Ubuntu/Debian : python3, python3-pip, python3-venv .deb files
                  (on a same-version online box: apt-get download python3 python3-pip python3-venv)
  RHEL/CentOS   : python3, python3-pip .rpm files

If the machine HAS internet, ignore this folder — bootstrap installs Python
via the OS package manager (apt/dnf/yum) or winget.
'@
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'installers\README.txt'),
    ($installersReadme -replace "`r`n", "`n"),
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host '  OK bootstrap.sh / bootstrap.ps1 / installers/'

# Write .gitignore (protect sensitive files in deploy package) ---------------
$gitignoreContent = @'
# 由 deploy.sh 更新
system/.env
# 部署憑證（含密碼）
deploy-init.env
'@
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir '.gitignore'),
    ($gitignoreContent -replace "`r`n", "`n"),
    (New-Object System.Text.UTF8Encoding $false)
)

# Write systemd service template --------------------------------------------
Write-Host 'Generating form-system.service...'
$systemdContent = @'
[Unit]
Description=Form System Backend
After=network.target postgresql.service swtpm.service

[Service]
Type=simple
User=form-system
WorkingDirectory=__SYS_ROOT__/backend
ExecStart=__SYS_ROOT__/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=__SYS_ROOT__/.env
StandardOutput=append:__SYS_ROOT__/logs/backend.log
StandardError=append:__SYS_ROOT__/logs/backend.log

[Install]
WantedBy=multi-user.target
'@
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'form-system.service'),
    ($systemdContent -replace "`r`n", "`n"),
    (New-Object System.Text.UTF8Encoding $false)
)

# Inject signing public key into staged license.py --------------------------
Write-Host 'Injecting signing public key into staged license.py...'
$pubKeyPath = Join-Path $PSScriptRoot 'keys\signing-public-key.pem'
if (-not (Test-Path $pubKeyPath)) {
    throw "signing-public-key.pem not found at $pubKeyPath. Run tools\generate-license-keys.ps1 first."
}
$pubKeyContent = [System.IO.File]::ReadAllText($pubKeyPath, [System.Text.Encoding]::UTF8).Trim().Replace("`r`n", "`n")
$stagedLicensePy = Join-Path $stageDir 'system\backend\app\core\license.py'
if (-not (Test-Path $stagedLicensePy)) {
    throw "license.py not found in staged system at $stagedLicensePy — check that assemble-system.ps1 includes platform-core-kit."
}
$licPyRaw = [System.IO.File]::ReadAllText($stagedLicensePy, [System.Text.Encoding]::UTF8).Replace("`r`n", "`n")
$beginMarker = '_PUBLIC_KEY_PEM = """'
$tripleQuote  = '"""'
$mStart = $licPyRaw.IndexOf($beginMarker)
if ($mStart -eq -1) { throw "Cannot find _PUBLIC_KEY_PEM assignment in staged license.py — injection anchor has changed." }
$mEnd = $licPyRaw.IndexOf($tripleQuote, $mStart + $beginMarker.Length)
if ($mEnd -eq -1) { throw "Cannot find closing triple-quote for _PUBLIC_KEY_PEM in staged license.py." }
$licPyNew = $licPyRaw.Substring(0, $mStart) +
    $beginMarker + "`n" + $pubKeyContent + "`n" +
    $licPyRaw.Substring($mEnd)
[System.IO.File]::WriteAllText($stagedLicensePy, $licPyNew, (New-Object System.Text.UTF8Encoding $false))
Write-Host "  OK  $stagedLicensePy"

# Sign package (requires tools/keys/signing-private-key.pem) ---------------
$signScript = Join-Path $PSScriptRoot 'sign-package.ps1'
$privKey    = Join-Path $PSScriptRoot 'keys\signing-private-key.pem'
if ((-not (Test-Path $signScript)) -or (-not (Test-Path $privKey))) {
    throw 'Cannot build deploy package: no signing key found at tools\keys\signing-private-key.pem. The backend enforces a license at startup, so a package without a signed license.lic would crash-loop. Run tools\generate-license-keys.ps1 (and ensure tools\sign-package.ps1 exists) before packaging.'
}

Write-Host 'Signing package...'
$recipeMachineId = if ($recipe.machineFingerprint) { [string]$recipe.machineFingerprint } else { '' }
$signArgs = @(
    '-ExecutionPolicy', 'Bypass',
    '-File', $signScript,
    '-RecipePath', $recipePath,
    '-PackageZipPath', $zipPath,
    '-PrivateKeyPath', $privKey,
    '-OutputDir', $stageDir,
    '-LicenseeName', $(if ($LicenseeName) { $LicenseeName } else { '__none__' }),
    '-LicenseeEmail', $(if ($LicenseeEmail) { $LicenseeEmail } else { '__none__' }),
    '-ExpiresAfterDays', ([string]$ExpiresAfterDays),
    '-MachineId', $(if ($recipeMachineId) { $recipeMachineId } else { '__none__' })
)
& powershell @signArgs
$licFile = Join-Path $stageDir 'license.lic'
if (Test-Path $licFile) {
    $systemDir = Join-Path $stageDir 'system'
    New-Item -ItemType Directory -Path $systemDir -Force | Out-Null
    Copy-Item $licFile (Join-Path $systemDir 'license.lic') -Force
}

# Create ZIP ----------------------------------------------------------------
if (-not $SkipZip) {
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path (Join-Path $stageDir '*') -DestinationPath $zipPath -Force
    Write-Host ('Client deploy zip: ' + $zipPath)
    if (Test-Path $licFile) {
        Compress-Archive -Path $licFile -DestinationPath $zipPath -Update
        Write-Host 'license.lic added to zip'
    }
} else {
    Write-Host ('Client deploy folder: ' + $stageDir)
}
