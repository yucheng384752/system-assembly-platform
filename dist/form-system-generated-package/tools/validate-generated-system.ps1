param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$GeneratedSystemDirectory = "dist\generated-system"
)

$ErrorActionPreference = "Stop"

$root = Join-Path $ProjectRoot $GeneratedSystemDirectory
$requiredPaths = @(
    "backend\app\main.py",
    "backend\app\core\backend_router_registry.py",
    "frontend",
    "scripts\check-prerequisites.ps1",
    "scripts\check-db.ps1",
    "scripts\install.ps1",
    "scripts\migrate.ps1",
    "scripts\smoke-start.ps1",
    "scripts\status.ps1",
    "scripts\stop.ps1",
    "scripts\restart.ps1",
    "scripts\start.ps1",
    ".env.example",
    "dependency-manifest.json",
    "dependency-plan.json",
    "db-bootstrap-plan.json",
    "backend\app\core\generated_db_bootstrap.py",
    "backend\app\models\__init__.py",
    "backend\requirements.txt",
    "frontend\package.json",
    "package-manifest.json",
    "README.md"
)

$missing = New-Object System.Collections.Generic.List[string]
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path (Join-Path $root $relativePath))) {
        $missing.Add($relativePath)
    }
}

if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Error "Missing generated system path: $_" }
    throw "Generated system validation failed"
}

Write-Host "OK $GeneratedSystemDirectory"
