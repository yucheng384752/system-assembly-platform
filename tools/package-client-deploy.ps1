param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$RecipeName  = '',
    [string]$OutputDir   = 'dist',
    [switch]$SkipZip
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

# Build deploy.sh -----------------------------------------------------------
# Rules: single-quoted PS strings keep bash $ literal; concatenate for PS vars
Write-Host 'Generating deploy.sh...'
$bar = '=' * 64
$sq  = [char]39   # single-quote for bash (Let's Encrypt etc.)
$L = [System.Collections.Generic.List[string]]::new()
$L.Add('#!/usr/bin/env bash')
$L.Add('# ' + $bar)
$L.Add('#  Form System Kit Composer - Server Deploy Script (Linux / macOS)')
$L.Add('#  Recipe : ' + $rName)
$L.Add('#  Built  : ' + $dateStr)
$L.Add('#  Kits   : ' + $rKits)
$L.Add('#  DB     : ' + $rDb)
$L.Add('# ' + $bar)
$L.Add('#')
$L.Add('#  Usage:')
$L.Add('#    bash deploy.sh                            # auto-detect system/ next to this script')
$L.Add('#    bash deploy.sh /opt/form-system           # specify system directory')
$L.Add('#    bash deploy.sh /opt/form-system --background  # start in background')
$L.Add('')
$L.Add('set -uo pipefail')
$L.Add('')
$L.Add('die()  { echo "" >&2; echo "[ERROR] $*" >&2; echo "" >&2; exit 1; }')
$L.Add('info() { echo "  $*"; }')
$L.Add('ok()   { echo "  OK $*"; }')
$L.Add('')
$L.Add('_MISSING=0')
$L.Add('check_cmd() {')
$L.Add('    if command -v "$1" >/dev/null 2>&1; then')
$L.Add('        ok "$1  $($1 --version 2>/dev/null | head -1)"')
$L.Add('    else')
$L.Add('        info "MISSING: $1  -> $2"')
$L.Add('        _MISSING=$((_MISSING + 1))')
$L.Add('    fi')
$L.Add('}')
$L.Add('')
$L.Add('check_prerequisites() {')
$L.Add('    echo "=== Prerequisites ==="')
$L.Add('    _MISSING=0')
$L.Add('    check_cmd python3 "https://www.python.org/downloads/"')
$L.Add('    check_cmd pip3    "installed with Python: python3 -m ensurepip"')
$L.Add('    check_cmd node    "https://nodejs.org/"')
$L.Add('    check_cmd npm     "installed with Node.js"')
$L.Add('    echo ""')
$L.Add('    if [ "${_MISSING}" -gt 0 ]; then')
$L.Add('        die "${_MISSING} required tools missing. Install and retry."')
$L.Add('    fi')
$L.Add('    ok "All prerequisites present"')
$L.Add('    echo ""')
$L.Add('}')
$L.Add('')
$L.Add('SCRIPT_DIR="$(cd "$(dirname "$0")" ; pwd)"')
$L.Add('SYS_ROOT=""')
$L.Add('BACKGROUND=0')
$L.Add('for _arg in "$@"; do')
$L.Add('    case "$_arg" in')
$L.Add('        --background) BACKGROUND=1 ;;')
$L.Add('        --*) die "Unknown option: $_arg" ;;')
$L.Add('        *) SYS_ROOT="$_arg" ;;')
$L.Add('    esac')
$L.Add('done')
$L.Add('')
$L.Add('if [ -z "${SYS_ROOT}" ]; then')
$L.Add('    for _c in "$SCRIPT_DIR/system" "$SCRIPT_DIR/generated-system"; do')
$L.Add('        if [ -d "$_c" ]; then SYS_ROOT="$_c"; break; fi')
$L.Add('    done')
$L.Add('fi')
$L.Add('if [ -z "${SYS_ROOT}" ]; then')
$L.Add('    die "Cannot find system dir. Usage: bash deploy.sh /path/to/system"')
$L.Add('fi')
$L.Add('if [ ! -d "${SYS_ROOT}" ]; then')
$L.Add('    die "Directory not found: ${SYS_ROOT}"')
$L.Add('fi')
$L.Add('SYS_ROOT="$(cd "${SYS_ROOT}" ; pwd)"')
$L.Add('if [ ! -f "${SYS_ROOT}/backend/requirements.txt" ]; then')
$L.Add('    die "backend/requirements.txt not found. Verify path is the assembled system dir."')
$L.Add('fi')
$L.Add('')
$L.Add('echo ""')
$L.Add('echo "Form System Kit Composer - Deploy"')
$L.Add('echo "Recipe  : ' + $rName + '"')
$L.Add('echo "SysRoot : ${SYS_ROOT}"')
$L.Add('echo ""')
$L.Add('')
$L.Add('check_prerequisites')
$L.Add('')
$L.Add('echo "=== Installing dependencies ==="')
$L.Add('pip3 install -r "${SYS_ROOT}/backend/requirements.txt"')
$L.Add('ok "Backend dependencies installed"')
$L.Add('if [ -f "${SYS_ROOT}/frontend/package.json" ]; then')
$L.Add('    npm --prefix "${SYS_ROOT}/frontend" install')
$L.Add('    ok "Frontend dependencies installed"')
$L.Add('fi')
$L.Add('echo ""')
$L.Add('')
$L.Add('echo "=== Database migration ==="')
$L.Add('if [ -f "${SYS_ROOT}/.env" ]; then')
$L.Add('    set -a ; . "${SYS_ROOT}/.env" ; set +a')
$L.Add('    info "Loaded ${SYS_ROOT}/.env"')
$L.Add('fi')
$L.Add('if [ -z "${DATABASE_URL:-}" ]; then')
$L.Add('    die "DATABASE_URL not set. Create ${SYS_ROOT}/.env with DATABASE_URL=postgresql+asyncpg://..."')
$L.Add('fi')
$L.Add('(cd "${SYS_ROOT}/backend" ; python3 -m alembic upgrade head)')
$L.Add('ok "Database migration complete"')
$L.Add('echo ""')
$L.Add('')
$L.Add('echo "=== Deploy complete ==="')
$L.Add('if [ "${BACKGROUND}" -eq 1 ]; then')
$L.Add('    mkdir -p "${SYS_ROOT}/logs"')
$L.Add('    (cd "${SYS_ROOT}/backend" ; nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >"${SYS_ROOT}/logs/backend.log" 2>&1 &')
$L.Add('    echo "$!" >"${SYS_ROOT}/logs/backend.pid")')
$L.Add('    ok "Backend running in background on port 8000"')
$L.Add('    info "Log: ${SYS_ROOT}/logs/backend.log"')
$L.Add('    if [ -f "${SYS_ROOT}/frontend/package.json" ]; then')
$L.Add('        info "Frontend: cd ${SYS_ROOT}/frontend && npm run dev"')
$L.Add('    fi')
$L.Add('else')
$L.Add('    info "Start backend:"')
$L.Add('    info "  cd ${SYS_ROOT}/backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"')
$L.Add('    if [ -f "${SYS_ROOT}/frontend/package.json" ]; then')
$L.Add('        info "Start frontend (separate terminal):"')
$L.Add('        info "  cd ${SYS_ROOT}/frontend && npm run dev"')
$L.Add('    fi')
$L.Add('fi')
$L.Add('echo ""')
$L.Add('echo "------------------------------------------------------"')
$L.Add('echo "  WARNING: Production checklist"')
$L.Add('echo "------------------------------------------------------"')
$L.Add('info "1. Do NOT run as root. Create a system user:"')
$L.Add('info "     sudo useradd -r -s /bin/false form-system"')
$L.Add('info "2. uvicorn has no TLS. Put a reverse proxy in front:"')
$L.Add('info "     nginx + certbot (Let' + $sq + 's Encrypt) or Caddy"')
$L.Add('info "3. Verify DATABASE_URL password is not the default"')
$L.Add('info "4. Set ENVIRONMENT=production to disable /docs"')
$L.Add('info "5. Run: pip-audit  and  npm audit  (CVE check)"')
$L.Add('echo ""')

$deployShContent = $L -join "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'deploy.sh'),
    $deployShContent,
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
$R.Add('├── system/      <- Assembled system (backend + frontend + scripts)')
$R.Add('├── deploy.sh    <- Deploy script (Linux / macOS)')
$R.Add('└── recipe.json  <- Assembly recipe')
$R.Add($tick3)
$R.Add('')
$R.Add('## Deployment steps (Ubuntu / macOS)')
$R.Add('')
$R.Add('### 1. Configure environment')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('cp system/.env.example system/.env')
$R.Add('nano system/.env')
$R.Add($tick3)
$R.Add('')
$R.Add('Required settings:')
$R.Add('')
$R.Add($tick3)
$R.Add('DATABASE_URL=postgresql+asyncpg://user:strongpassword@localhost:5432/form_db')
$R.Add('SECRET_KEY=<random 64-character string>')
$R.Add('ENVIRONMENT=production')
$R.Add($tick3)
$R.Add('')
$R.Add('Generate a strong SECRET_KEY:')
$R.Add($tick3 + 'bash')
$R.Add('python3 -c "import secrets; print(secrets.token_urlsafe(48))"')
$R.Add($tick3)
$R.Add('')
$R.Add('### 2. Run deploy')
$R.Add('')
$R.Add($tick3 + 'bash')
$R.Add('bash deploy.sh                 # install + migrate + show start commands')
$R.Add('bash deploy.sh --background    # install + migrate + start in background')
$R.Add($tick3)
$R.Add('')
$R.Add('## Production security checklist')
$R.Add('')
$R.Add('- [ ] Do NOT run as root: ' + $tick1 + 'sudo useradd -r -s /bin/false form-system' + $tick1)
$R.Add('- [ ] Set up nginx/caddy + TLS (Let' + $sq + 's Encrypt)')
$R.Add('- [ ] ' + $tick1 + 'SECRET_KEY' + $tick1 + ' is a strong random value (not the default)')
$R.Add('- [ ] ' + $tick1 + 'DATABASE_URL' + $tick1 + ' uses a strong password (not the default)')
$R.Add('- [ ] ' + $tick1 + 'ENVIRONMENT=production' + $tick1 + ' is set (disables /docs)')
$R.Add('- [ ] Run ' + $tick1 + 'pip-audit' + $tick1 + ' and ' + $tick1 + 'npm audit' + $tick1)
$R.Add('- [ ] Rotate API keys and SECRET_KEY periodically')

$readmeContent = $R -join "`n"
[System.IO.File]::WriteAllText(
    (Join-Path $stageDir 'README.md'),
    $readmeContent,
    (New-Object System.Text.UTF8Encoding $false)
)

# Copy recipe.json ----------------------------------------------------------
Copy-Item $recipePath (Join-Path $stageDir 'recipe.json') -Force

# Create ZIP ----------------------------------------------------------------
if (-not $SkipZip) {
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path (Join-Path $stageDir '*') -DestinationPath $zipPath -Force
    Write-Host ('Client deploy zip: ' + $zipPath)
} else {
    Write-Host ('Client deploy folder: ' + $stageDir)
}
