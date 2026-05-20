param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$appPath = Join-Path $ProjectRoot "gui\app.js"
$indexPath = Join-Path $ProjectRoot "gui\index.html"
$stylePath = Join-Path $ProjectRoot "gui\styles.css"

node --check $appPath | Out-Null

$app = Get-Content -Raw -Encoding UTF8 $appPath
$index = Get-Content -Raw -Encoding UTF8 $indexPath
$style = Get-Content -Raw -Encoding UTF8 $stylePath

$requiredAppSnippets = @(
    "function buildRecipe()",
    "sourceManifest",
    "selectedSubfeatures",
    "selectedSubfeatureOptions",
    "function recipeJsonText()",
    "function assemblyCommands()",
    "copyRecipeJson",
    "downloadRecipeJson"
)

$requiredIndexSnippets = @(
    "recipe-output",
    "copy-recipe-json",
    "download-recipe-json",
    "assembly-command-list"
)

$requiredStyleSnippets = @(
    ".recipe-output",
    ".action-row"
)

foreach ($snippet in $requiredAppSnippets) {
    if (-not $app.Contains($snippet)) {
        throw "GUI recipe export app missing snippet: $snippet"
    }
}

foreach ($snippet in $requiredIndexSnippets) {
    if (-not $index.Contains($snippet)) {
        throw "GUI recipe export index missing snippet: $snippet"
    }
}

foreach ($snippet in $requiredStyleSnippets) {
    if (-not $style.Contains($snippet)) {
        throw "GUI recipe export style missing snippet: $snippet"
    }
}

Write-Host "OK GUI recipe export"
