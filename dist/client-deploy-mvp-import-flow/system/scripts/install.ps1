param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$requirements = Join-Path $Root "backend\requirements.txt"
$pyproject = Join-Path $Root "backend\pyproject.toml"
$frontendPackage = Join-Path $Root "frontend\package.json"

if (Test-Path $requirements) {
    Write-Host "Installing backend dependencies from backend\requirements.txt"
    & $Python -m pip install -r $requirements
} elseif (Test-Path $pyproject) {
    Write-Host "Installing backend project from backend\pyproject.toml"
    Push-Location (Join-Path $Root "backend")
    try {
        & $Python -m pip install .
    } finally {
        Pop-Location
    }
} else {
    throw "Backend dependency manifest is missing. Add backend\requirements.txt or backend\pyproject.toml before running install."
}

if (-not $SkipFrontend) {
    if (Test-Path $frontendPackage) {
        Write-Host "Installing frontend dependencies from frontend\package.json"
        Push-Location (Join-Path $Root "frontend")
        try {
            & $Npm install
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning "frontend\package.json is missing; skipping frontend install."
    }
}

Write-Host "Install step completed."
