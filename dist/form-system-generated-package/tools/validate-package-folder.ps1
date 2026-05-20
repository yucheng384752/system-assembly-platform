param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$PackageDirectory = "dist\form-system-generated-package"
)

$ErrorActionPreference = "Stop"

$packagePath = Join-Path $ProjectRoot $PackageDirectory
$requiredPaths = @(
    "README.md",
    "TODO.md",
    "HANDOFF.md",
    "docs\kit-development-standard.md",
    "kits\form-analysis.kit-manifest.json",
    "schemas\kit.schema.json",
    "schemas\recipe.schema.json",
    "assembly\resolved-plan.json",
    "assembly\mvp-resolved-plan.json",
    "assembly\backend-registry\backend_router_registry.py",
    "assembly\backend-registry-mvp\backend_router_registry.py",
    "assembly\frontend-registry\frontend-tab-registry.json",
    "assembly\db-plan\db-assembly-plan.json",
    "assembly\entitlement-plan\entitlement-plan.json",
    "tools\assemble-system.ps1",
    "tools\generate-dependency-files.ps1",
    "tools\generate-db-bootstrap.ps1",
    "tools\generate-model-init.ps1",
    "tools\apply-upload-page-refactor.ps1",
    "tools\test-dependency-files.ps1",
    "tools\test-db-bootstrap.ps1",
    "tools\test-generated-start.ps1",
    "tools\test-process-supervision.ps1",
    "tools\test-gui-recipe-export.ps1",
    "tools\test-upload-page-refactor.ps1",
    "tools\test-gui-browser.ps1",
    "generated\mvp-import-flow\form-analysis-server\backend\app\main.py"
)

$missing = New-Object System.Collections.Generic.List[string]
foreach ($relativePath in $requiredPaths) {
    $path = Join-Path $packagePath $relativePath
    if (-not (Test-Path $path)) {
        $missing.Add($relativePath)
    }
}

if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Error "Missing package path: $_" }
    throw "Package folder validation failed"
}

Write-Host "OK $PackageDirectory"
