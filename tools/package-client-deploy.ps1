param(
    [string]$ProjectRoot      = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$RecipeName       = '',
    [string]$OutputDir        = 'dist',
    [switch]$SkipZip,
    [string]$LicenseeName     = '',
    [string]$LicenseeEmail    = '',
    [int]$ExpiresAfterDays    = 0
)

$ErrorActionPreference = 'Stop'

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

# Validate generated-system -------------------------------------------------
$sysRoot = Join-Path $ProjectRoot 'dist\generated-system'
if (-not (Test-Path (Join-Path $sysRoot 'backend\requirements.txt'))) {
    throw 'Generated system not found. Run tools\assemble-system.ps1 first.'
}

# Stage directory -----------------------------------------------------------
$outRoot  = Join-Path $ProjectRoot $OutputDir
$stageDir = Join-Path $outRoot ('client-deploy-' + $rName)
$zipPath  = $stageDir + '.zip'

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
#    bash deploy.sh
#    bash deploy.sh --interactive
#    bash deploy.sh /opt/form-system --background
#    bash deploy.sh /opt/form-system --interactive --background

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
echo "Recipe  : __RNAME__"
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
'@

$deployShContent = $deployShContent.Replace('__BAR__', $bar).Replace('__RNAME__', $rName).Replace('__DATE__', $dateStr).Replace('__RKITS__', $rKits).Replace('__RDB__', $rDb).Replace('__ASK_AUTH__', $askAuth).Replace('__ASK_PDF__', $askPdf).Replace('__ASK_VALIDATION__', $askValidation)
$deployShContent = $deployShContent -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'deploy.sh'),
    $deployShContent,
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
            npm install --silent
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
        "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"
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
    try { & $Python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 }
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
$R.Add('client-deploy-' + $rName + '/')
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
$R.Add('unzip client-deploy-' + $rName + '.zip')
$R.Add('cd client-deploy-' + $rName)
$R.Add($tick3)
$R.Add('')
$R.Add('### 2. Configure environment')
$R.Add('')
$R.Add('Interactive setup:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash deploy.sh --interactive')
$R.Add($tick3)
$R.Add('')
$R.Add('Non-interactive setup:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('cp system/.env.example system/.env')
$R.Add('nano system/.env')
$R.Add('bash deploy.sh')
$R.Add($tick3)
$R.Add('')
$R.Add('Required settings include:')
$R.Add('')
$R.Add($tick3)
$R.Add('DATABASE_URL=postgresql+asyncpg://user:strongpassword@localhost:5432/form_db')
$R.Add('SECRET_KEY=<random 64-character string>')
$R.Add('CORS_ORIGINS=http://localhost:5173,http://localhost:3000')
$R.Add('AUTH_MODE=api_key')
$R.Add('ADMIN_API_KEYS=<comma-separated random keys>')
$R.Add('ENVIRONMENT=production')
$R.Add($tick3)
$R.Add('')
$R.Add('Generate a strong SECRET_KEY:')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('python3 -c "import secrets; print(secrets.token_urlsafe(48))"')
$R.Add($tick3)
$R.Add('')
$R.Add('### 3. Run deploy script')
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
$R.Add('5. Builds the frontend (' + $tick1 + 'npm install' + $tick1 + ' + ' + $tick1 + 'npm run build' + $tick1 + ')')
$R.Add('6. Runs database migrations (' + $tick1 + 'alembic upgrade head' + $tick1 + ' or ' + $tick1 + 'generated_db_bootstrap.py' + $tick1 + ')')
$R.Add('')
$R.Add('### 4. Start the backend')
$R.Add('')
$R.Add('**Option A - foreground (for testing):**')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('cd system/backend')
$R.Add('../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000')
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
RUN npm install --silent && npm run build

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

server {
    listen 80;
    server_name _;

    # Update to the absolute path where you extracted the deploy package
    root /opt/form-system/client-deploy-__RNAME__/system/frontend/dist;
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
$nginxStandaloneContent = $nginxStandaloneContent.Replace('__RNAME__', $rName) -replace "`r`n", "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'nginx.conf'),
    $nginxStandaloneContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# Copy recipe.json ----------------------------------------------------------
Copy-Item $recipePath (Join-Path $stageDir 'recipe.json') -Force

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
After=network.target postgresql.service

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

# Create ZIP ----------------------------------------------------------------
if (-not $SkipZip) {
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path (Join-Path $stageDir '*') -DestinationPath $zipPath -Force
    Write-Host ('Client deploy zip: ' + $zipPath)

    # Sign package (requires tools/keys/signing-private-key.pem) ---------------
    $signScript = Join-Path $PSScriptRoot 'sign-package.ps1'
    $privKey    = Join-Path $PSScriptRoot 'keys\signing-private-key.pem'
    if ((Test-Path $signScript) -and (Test-Path $privKey)) {
        Write-Host 'Signing package...'
        & powershell -ExecutionPolicy Bypass -File $signScript `
            -RecipePath $recipePath `
            -PackageZipPath $zipPath `
            -PrivateKeyPath $privKey `
            -OutputDir $stageDir `
            -LicenseeName $LicenseeName `
            -LicenseeEmail $LicenseeEmail `
            -ExpiresAfterDays $ExpiresAfterDays
        # Copy license.lic into zip (re-compress with license)
        $licFile = Join-Path $stageDir 'license.lic'
        if (Test-Path $licFile) {
            Compress-Archive -Path $licFile -DestinationPath $zipPath -Update
            Write-Host 'license.lic added to zip'
        }
    } else {
        Write-Host 'SKIP signing (no private key found). Run tools\generate-license-keys.ps1 to enable.'
    }
} else {
    Write-Host ('Client deploy folder: ' + $stageDir)
}
