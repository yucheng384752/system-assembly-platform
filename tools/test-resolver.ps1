param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

& (Join-Path $ProjectRoot "tools\resolve-recipe.ps1") -ProjectRoot $ProjectRoot | Out-Null
& (Join-Path $ProjectRoot "tools\resolve-recipe.ps1") `
    -ProjectRoot $ProjectRoot `
    -RecipePath "assembly\mvp-import-flow.recipe.json" `
    -OutputPath "assembly\mvp-resolved-plan.json" | Out-Null

$fullPlan = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "assembly\resolved-plan.json") | ConvertFrom-Json
$mvpPlan = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "assembly\mvp-resolved-plan.json") | ConvertFrom-Json

if (@($fullPlan.missing).Count -ne 0) {
    throw "Full resolver has missing entries"
}
if (@($mvpPlan.missing).Count -ne 0) {
    throw "MVP resolver has missing entries"
}
if (-not @($mvpPlan.backendRouterRegistrations).Count) {
    throw "MVP resolver did not emit backendRouterRegistrations"
}

Write-Host "OK resolver smoke"
