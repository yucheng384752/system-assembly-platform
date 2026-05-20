param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$OutputDirectory = "dist",
    [string]$PackageDirectoryName = "form-system-generated-package",
    [string]$PackageName = "form-system-generated-package.zip",
    [switch]$CreateZip
)

$ErrorActionPreference = "Stop"

function Copy-IfExists([string]$Source, [string]$DestinationRoot) {
    $sourcePath = Join-Path $ProjectRoot $Source
    if (-not (Test-Path $sourcePath)) {
        return
    }

    $destinationPath = Join-Path $DestinationRoot $Source
    $destinationParent = Split-Path -Parent $destinationPath
    if (-not (Test-Path $destinationParent)) {
        New-Item -ItemType Directory -Force $destinationParent | Out-Null
    }

    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force
}

function New-CleanDirectory([string]$Path) {
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force $Path | Out-Null
}

$outputRoot = Join-Path $ProjectRoot $OutputDirectory
$stageRoot = Join-Path $outputRoot $PackageDirectoryName
$packagePath = Join-Path $outputRoot $PackageName

New-Item -ItemType Directory -Force $outputRoot | Out-Null
New-CleanDirectory $stageRoot

$paths = @(
    "README.md",
    "TODO.md",
    "HANDOFF.md",
    "kits\form-analysis.kit-manifest.json",
    "schemas\kit.schema.json",
    "schemas\recipe.schema.json",
    "assembly\form-analysis-original.recipe.json",
    "assembly\mvp-import-flow.recipe.json",
    "assembly\resolved-plan.json",
    "assembly\mvp-resolved-plan.json",
    "assembly\backend-registry",
    "assembly\backend-registry-mvp",
    "assembly\frontend-registry",
    "assembly\db-plan",
    "assembly\entitlement-plan",
    "tools\validate-json.ps1",
    "tools\validate-recipe.ps1",
    "tools\resolve-recipe.ps1",
    "tools\generate-backend-registry.ps1",
    "tools\generate-frontend-registry.ps1",
    "tools\generate-db-plan.ps1",
    "tools\generate-db-bootstrap.ps1",
    "tools\generate-model-init.ps1",
    "tools\generate-entitlement-plan.ps1",
    "tools\generate-dependency-files.ps1",
    "tools\apply-backend-registry.ps1",
    "tools\apply-upload-page-refactor.ps1",
    "tools\extract-mvp-flow.ps1",
    "tools\assemble-system.ps1",
    "tools\validate-package-folder.ps1",
    "tools\validate-generated-system.ps1",
    "tools\test-gui-browser.mjs",
    "tools\test-gui-browser.ps1",
    "tools\test-dependency-files.ps1",
    "tools\test-db-bootstrap.ps1",
    "tools\test-generated-start.ps1",
    "tools\test-process-supervision.ps1",
    "tools\test-gui-recipe-export.ps1",
    "tools\test-upload-page-refactor.ps1",
    "tools\test-gui-static.ps1",
    "tools\test-resolver.ps1",
    "tools\test-all.ps1",
    "tools\package-system.ps1",
    "tools\README.md",
    "docs\product-requirements.zh-TW.md",
    "docs\gui-production-spec.md",
    "docs\kit-expansion-strategy.md",
    "docs\kit-development-standard.md",
    "docs\decomposition-process.md",
    "docs\system-decomposition.md",
    "templates",
    "generated\mvp-import-flow"
)

foreach ($path in $paths) {
    Copy-IfExists $path $stageRoot
}

$manifest = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    packageDirectory = $PackageDirectoryName
    purpose = "Form System Kit Composer generated folder"
    runnablePackageStatus = "selection-and-mvp-source-snapshot"
    includedPaths = $paths
}

$manifestPath = Join-Path $stageRoot "package-manifest.json"
$manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $manifestPath

if ($CreateZip) {
    if (Test-Path $packagePath) {
        Remove-Item -LiteralPath $packagePath -Force
    }

    Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $packagePath -Force
    Write-Host "Package zip written to $packagePath"
    return
}

Write-Host "Package folder written to $stageRoot"
if (Test-Path $packagePath) {
    Write-Host "Existing zip was not updated. Use -CreateZip only when archive testing is explicitly needed."
}
