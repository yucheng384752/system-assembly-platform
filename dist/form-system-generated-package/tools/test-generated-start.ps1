param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$GeneratedSystemDirectory = "dist\generated-system"
)

$ErrorActionPreference = "Stop"

$root = Join-Path $ProjectRoot $GeneratedSystemDirectory
if (-not (Test-Path $root)) {
    & (Join-Path $ProjectRoot "tools\assemble-system.ps1") -ProjectRoot $ProjectRoot
}

$python = "C:\Users\gslab\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$requiredPaths = @(
    "backend\app\models\__init__.py",
    "backend\app\models\base_record.py",
    "backend\app\models\core\tenant.py",
    "backend\app\models\core\tenant_user.py",
    "backend\app\models\core\tenant_api_key.py",
    "backend\app\models\core\schema_registry.py",
    "backend\app\models\station.py",
    "backend\app\models\upload_job.py",
    "backend\app\models\import_job.py",
    "scripts\smoke-start.ps1"
)

foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path (Join-Path $root $relativePath))) {
        throw "Missing generated start validation path: $relativePath"
    }
}

$smokeScript = Get-Content -Raw -Encoding UTF8 (Join-Path $root "scripts\smoke-start.ps1")
if ($smokeScript -notmatch "Invoke-CheckedNative") {
    throw "scripts\smoke-start.ps1 does not check native command exit codes."
}

& (Join-Path $root "scripts\smoke-start.ps1") -Python $python | Out-Host

Write-Host "OK generated start validation"
