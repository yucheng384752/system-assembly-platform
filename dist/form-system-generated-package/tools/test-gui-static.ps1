param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$appPath = Join-Path $ProjectRoot "gui\app.js"
$indexPath = Join-Path $ProjectRoot "gui\index.html"

node --check $appPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "GUI app syntax check failed: $appPath"
}

$app = Get-Content -Raw -Encoding UTF8 $appPath
$index = Get-Content -Raw -Encoding UTF8 $indexPath

$requiredAppSnippets = @(
    "const flows = [",
    "data-flow-toggle",
    "data-subflow-toggle",
    "function buildRecipe()",
    "machinePubkey",
    "handleMachinePubkeyFile",
    "gate-machine-pubkey-file",
    "valueToPk",
    "clientTableCode",
    "dataflows:",
    "edgeCreatesCycle",
    "fromTableCode"
)
$requiredIndexSnippets = @(
    "machine-gate-overlay",
    "gate-machine-pubkey-file",
    "client-name",
    "dataflow-select",
    "flow-grid",
    "kit-grid",
    "generation-summary"
)

foreach ($snippet in $requiredAppSnippets) {
    if (-not $app.Contains($snippet)) {
        throw "GUI app missing snippet: $snippet"
    }
}
foreach ($snippet in $requiredIndexSnippets) {
    if (-not $index.Contains($snippet)) {
        throw "GUI index missing snippet: $snippet"
    }
}

Write-Host "OK gui static smoke"
