param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$envPath = Join-Path $Root ".env"
$envExamplePath = Join-Path $Root ".env.example"
if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created .env from .env.example"
}

$alembicIni = Join-Path $Root "backend\alembic.ini"
if (Test-Path $alembicIni) {
    Write-Host "Running Alembic migrations."
    Push-Location (Join-Path $Root "backend")
    try {
        & $Python -m alembic upgrade head
    } finally {
        Pop-Location
    }
} else {
    $bootstrapModule = Join-Path $Root "backend\app\core\generated_db_bootstrap.py"
    if (Test-Path $bootstrapModule) {
        Write-Host "Alembic is missing; running generated SQLAlchemy bootstrap."
        Push-Location (Join-Path $Root "backend")
        try {
            & $Python -m app.core.generated_db_bootstrap
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning "backend\alembic.ini and generated_db_bootstrap.py are missing; no migration command was run."
    }
}
