param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$planPath = Join-Path $Root "kitInstallPlan.json"
if (-not (Test-Path $planPath)) {
    throw "Kit install plan not found: $planPath"
}

$plan = Get-Content -Raw -Encoding UTF8 $planPath | ConvertFrom-Json
foreach ($entry in @($plan | Sort-Object order)) {
    $scriptPath = Join-Path $Root "kits\$($entry.kit)\install.ps1"
    if (-not (Test-Path $scriptPath)) {
        throw "Kit install script not found: $scriptPath"
    }

    Write-Host "Running kit install: $($entry.kit)"
    & powershell -ExecutionPolicy Bypass -File $scriptPath -Root $Root
    if ($LASTEXITCODE -ne 0) {
        throw "Kit install failed for $($entry.kit) with exit code $LASTEXITCODE."
    }
}

Write-Host "Kit install plan completed."
