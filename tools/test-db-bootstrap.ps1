param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$GeneratedSystemDirectory = "dist\generated-system"
)

$ErrorActionPreference = "Stop"

$root = Join-Path $ProjectRoot $GeneratedSystemDirectory
if (-not (Test-Path $root)) {
    & (Join-Path $ProjectRoot "tools\assemble-system.ps1") -ProjectRoot $ProjectRoot
}

& (Join-Path $ProjectRoot "tools\generate-db-bootstrap.ps1") `
    -ProjectRoot $ProjectRoot `
    -SystemDirectory $GeneratedSystemDirectory

$requiredPaths = @(
    "backend\app\core\generated_db_bootstrap.py",
    "scripts\check-db.ps1",
    "db-bootstrap-plan.json"
)

foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path (Join-Path $root $relativePath))) {
        throw "Missing DB bootstrap path: $relativePath"
    }
}

$migrateScript = Get-Content -Raw -Encoding UTF8 (Join-Path $root "scripts\migrate.ps1")
if ($migrateScript -notmatch "generated_db_bootstrap") {
    throw "scripts\migrate.ps1 does not call generated_db_bootstrap fallback."
}

$python = "C:\Users\gslab\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python -m py_compile (Join-Path $root "backend\app\core\generated_db_bootstrap.py")
& (Join-Path $root "scripts\check-db.ps1") -Python $python | Out-Host

Write-Host "OK DB bootstrap"
