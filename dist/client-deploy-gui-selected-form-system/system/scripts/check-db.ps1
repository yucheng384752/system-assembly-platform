param(
    [string]$Python = "python",
    [switch]$Connect
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$BackendRoot = Join-Path $Root "backend"
$BootstrapPath = Join-Path $BackendRoot "app\core\generated_db_bootstrap.py"
$EnvPath = Join-Path $Root ".env"
$EnvExamplePath = Join-Path $Root ".env.example"

if (-not (Test-Path $BootstrapPath)) {
    throw "Database bootstrap module is missing: backend\app\core\generated_db_bootstrap.py"
}

if (-not (Test-Path $EnvPath) -and (Test-Path $EnvExamplePath)) {
    Copy-Item -LiteralPath $EnvExamplePath -Destination $EnvPath
    Write-Host "Created .env from .env.example"
}

$summary = [ordered]@{
    root = $Root
    bootstrapModule = "backend\app\core\generated_db_bootstrap.py"
    envPresent = Test-Path $EnvPath
    connectRequested = [bool]$Connect
}
$summary | ConvertTo-Json -Depth 10

if ($Connect) {
    Push-Location $BackendRoot
    try {
        & $Python -m app.core.generated_db_bootstrap
    } finally {
        Pop-Location
    }
}
