param(
    [string]$SystemDir = "",
    [string]$PythonVersion = "3.11.9"
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$RepoRoot = Split-Path $ScriptDir -Parent

function Write-OK([string]$Message) { Write-Host "  [OK]   $Message" -ForegroundColor Green }
function Write-Info([string]$Message) { Write-Host "  [INFO] $Message" -ForegroundColor Yellow }
function Write-Warn([string]$Message) { Write-Host "  [WARN] $Message" -ForegroundColor DarkYellow }
function Die([string]$Message) { Write-Host "  [ERR]  $Message" -ForegroundColor Red; exit 1 }

Write-Host "======================================================"
Write-Host "  Form System Kit Composer offline dependency prep"
Write-Host "======================================================"

if (-not $SystemDir) {
    $candidates = @(
        (Join-Path $RepoRoot "dist\client-deploy-gui-selected-form-system\system"),
        (Join-Path $RepoRoot "dist\generated-system"),
        (Join-Path $RepoRoot "generated\mvp-import-flow\form-analysis-server")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate "backend\requirements.txt")) {
            $SystemDir = $candidate
            break
        }
    }
}

if (-not $SystemDir -or -not (Test-Path (Join-Path $SystemDir "backend\requirements.txt"))) {
    Die "System directory not found. Run tools\assemble-system.ps1 first or pass -SystemDir."
}
Write-OK "system dir: $SystemDir"

$BackendDir = Join-Path $SystemDir "backend"
$ReqFile = Join-Path $BackendDir "requirements.txt"
$WheelsDir = Join-Path $BackendDir "wheels"

if (-not (Test-Path $WheelsDir)) {
    New-Item -ItemType Directory -Force $WheelsDir | Out-Null
    Write-OK "created wheels dir: $WheelsDir"
} else {
    Write-Info "wheels dir exists, updating: $WheelsDir"
}

Write-Info "Downloading backend pip wheels..."
Write-Info "requirements.txt: $ReqFile"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Die "python not found. Install Python 3.10+ and retry."
}

& python -m pip download `
    --dest "$WheelsDir" `
    --platform linux_x86_64 `
    --python-version "310" `
    --only-binary=:all: `
    -r "$ReqFile"

if ($LASTEXITCODE -ne 0) {
    Write-Warn "linux_x86_64 wheel download failed, retrying without platform pin..."
    & python -m pip download `
        --dest "$WheelsDir" `
        -r "$ReqFile"
    if ($LASTEXITCODE -ne 0) {
        Die "pip download failed. Check network access and requirements.txt."
    }
}

$wheelCount = (Get-ChildItem $WheelsDir -Filter "*.whl" -ErrorAction SilentlyContinue).Count
$tarCount = (Get-ChildItem $WheelsDir -Filter "*.tar.gz" -ErrorAction SilentlyContinue).Count
Write-OK "backend wheels prepared: $wheelCount .whl + $tarCount .tar.gz"

$FrontendDir = Join-Path $SystemDir "frontend"
$PackageJson = Join-Path $FrontendDir "package.json"
$PackageLock = Join-Path $FrontendDir "package-lock.json"
$NpmCacheDir = Join-Path $FrontendDir ".npm-cache"

if ((Test-Path $PackageJson) -and (Test-Path $PackageLock)) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Die "npm not found. Install Node.js/npm before preparing frontend offline dependencies."
    }

    Write-Info "Downloading frontend npm cache from package-lock.json..."
    Push-Location $FrontendDir
    try {
        New-Item -ItemType Directory -Force $NpmCacheDir | Out-Null
        & npm ci --cache "$NpmCacheDir" --ignore-scripts --silent
        if ($LASTEXITCODE -ne 0) {
            Die "npm ci failed while preparing frontend npm cache."
        }
    } finally {
        Pop-Location
    }

    $nodeModulesPath = Join-Path $FrontendDir "node_modules"
    if (Test-Path $nodeModulesPath) {
        Remove-Item -LiteralPath $nodeModulesPath -Recurse -Force
    }
    Write-OK "frontend npm cache prepared: $NpmCacheDir"
} elseif (Test-Path $PackageJson) {
    Write-Warn "frontend package-lock.json missing; skipping npm offline cache."
}

# ── Bundle Windows Python installer for offline bootstrap ──────────────────
$DeployRoot = Split-Path $SystemDir -Parent
$InstallersDir = Join-Path $DeployRoot "installers"
if (Test-Path (Join-Path $DeployRoot "bootstrap.ps1")) {
    New-Item -ItemType Directory -Force $InstallersDir | Out-Null
    $existing = Get-ChildItem $InstallersDir -Include *.exe, *.msi -File -Recurse -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Info "Python installer already bundled: $($existing[0].Name)"
    } else {
        $pyUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
        $pyOut = Join-Path $InstallersDir "python-$PythonVersion-amd64.exe"
        Write-Info "Downloading Windows Python installer: $pyUrl"
        try {
            Invoke-WebRequest -Uri $pyUrl -OutFile $pyOut -UseBasicParsing
            Write-OK "bundled Python installer: $pyOut"
        } catch {
            Write-Warn "Could not download Python installer ($($_.Exception.Message)). Drop python-$PythonVersion-amd64.exe into installers/ manually."
        }
    }
    Write-Info "Linux offline target: place python3 .deb/.rpm into installers/ (see installers/README.txt)"
} else {
    Write-Info "No bootstrap.ps1 at deploy root; skipping Python installer bundling (run package-client-deploy.ps1 first)."
}

Write-Host ""
Write-Host "======================================================"
Write-Host "  Offline dependency preparation complete" -ForegroundColor Green
Write-Host "======================================================"
Write-Host "  wheels dir    : $WheelsDir"
if (Test-Path $NpmCacheDir) {
    Write-Host "  npm cache     : $NpmCacheDir"
}
Write-Host "  python files  : $($wheelCount + $tarCount)"
Write-Host ""
Write-Host "  Backend offline install:"
Write-Host "    pip install --find-links wheels/ --no-index -r requirements.txt"
Write-Host "  Frontend offline install:"
Write-Host "    npm ci --cache .npm-cache --offline"
Write-Host "======================================================"
