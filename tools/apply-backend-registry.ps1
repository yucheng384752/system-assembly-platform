param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$GeneratedAppRoot = "generated\mvp-import-flow\form-analysis-server",
    [string]$RegistrySource = "assembly\backend-registry-mvp\backend_router_registry.py"
)

$ErrorActionPreference = "Stop"

function Replace-Required([string]$Text, [string]$Pattern, [string]$Replacement, [string]$Description) {
    $updated = [regex]::Replace($Text, $Pattern, $Replacement, "Singleline")
    if ($updated -eq $Text) {
        throw "Failed to update $Description"
    }
    return $updated
}

$appRoot = Join-Path $ProjectRoot $GeneratedAppRoot
$registrySourcePath = Join-Path $ProjectRoot $RegistrySource
$registryTargetPath = Join-Path $appRoot "backend\app\core\backend_router_registry.py"
$mainPath = Join-Path $appRoot "backend\app\main.py"

if (-not (Test-Path $registrySourcePath)) {
    throw "Registry source not found: $registrySourcePath"
}
if (-not (Test-Path $mainPath)) {
    throw "Generated main.py not found: $mainPath"
}

$targetParent = Split-Path -Parent $registryTargetPath
if (-not (Test-Path $targetParent)) {
    New-Item -ItemType Directory -Force $targetParent | Out-Null
}
Copy-Item -LiteralPath $registrySourcePath -Destination $registryTargetPath -Force

$main = Get-Content -Raw -Encoding UTF8 $mainPath

$apiImportPattern = 'from app\.api import constants as routes_constants\r?\nfrom app\.api import \(\r?\n.*?\)\r?\nfrom app\.api import routes_stations, traceability as routes_traceability\r?\n'
$main = Replace-Required `
    -Text $main `
    -Pattern $apiImportPattern `
    -Replacement "" `
    -Description "hard-coded app.api router imports"

$databaseImport = "from app.core.database import Base, init_db"
if ($main -notmatch [regex]::Escape("from app.core.backend_router_registry import register_backend_routers")) {
    $main = $main.Replace(
        $databaseImport,
        "from app.core.backend_router_registry import register_backend_routers`r`n$databaseImport"
    )
}

$includePattern = '# Include API routers\r?\ntenant_deps = \[Depends\(get_current_tenant\)\]\r?\n.*?(?=\r?\n@app\.get\("/", tags=\["Root"\]\))'
$includeReplacement = @"
# Include API routers through the generated kit registry
tenant_deps = [Depends(get_current_tenant)]
register_backend_routers(app, tenant_deps=tenant_deps, settings=settings)

"@
$main = Replace-Required `
    -Text $main `
    -Pattern $includePattern `
    -Replacement $includeReplacement `
    -Description "hard-coded include_router block"

Set-Content -Encoding UTF8 $mainPath $main

Write-Host "Copied backend registry to $registryTargetPath"
Write-Host "Updated generated FastAPI router registration in $mainPath"
