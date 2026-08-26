#Requires -Version 5.1
<#
.SYNOPSIS
  Form System Kit Composer - Server Deploy Script (Windows)
  Recipe : gui-selected-form-system
  Built  : 2026-08-26 17:29

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