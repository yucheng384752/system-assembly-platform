param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$files = @(
    "kits\form-analysis.kit-manifest.json",
    "assembly\form-analysis-original.recipe.json",
    "assembly\mvp-import-flow.recipe.json",
    "schemas\kit.schema.json",
    "schemas\recipe.schema.json"
)

foreach ($file in $files) {
    $path = Join-Path $ProjectRoot $file
    Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json | Out-Null
    Write-Host "OK $file"
}
