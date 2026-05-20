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
    "architectureQuestions",
    "data-guide-choice",
    "data-subfeature-toggle",
    "data-subfeature-option",
    "mod-subscription-kit"
)
$requiredIndexSnippets = @(
    "architecture-guide",
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
