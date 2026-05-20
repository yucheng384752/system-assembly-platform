param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$Npm = "npm",
    [string]$Node = "node"
)

$ErrorActionPreference = "Stop"

$outputDir = Join-Path $ProjectRoot "output\playwright"
New-Item -ItemType Directory -Force $outputDir | Out-Null

$runnerDir = Join-Path $outputDir "runner"
New-Item -ItemType Directory -Force $runnerDir | Out-Null

$packageJson = Join-Path $runnerDir "package.json"
if (-not (Test-Path $packageJson)) {
    @{
        private = $true
        type = "module"
        dependencies = @{}
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $packageJson
}

$playwrightPackage = Join-Path $runnerDir "node_modules\playwright\package.json"
if (-not (Test-Path $playwrightPackage)) {
    & $Npm --prefix $runnerDir install playwright
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Playwright with exit code $LASTEXITCODE"
    }
}

$playwrightCli = Join-Path $runnerDir "node_modules\.bin\playwright.cmd"
if (-not (Test-Path $playwrightCli)) {
    throw "Playwright CLI was not installed at $playwrightCli"
}

$playwrightModule = Join-Path $runnerDir "node_modules\playwright"
$chromiumPath = & $Node -e "const { chromium } = require(process.argv[1]); console.log(chromium.executablePath());" $playwrightModule
if (-not (Test-Path $chromiumPath)) {
    & $playwrightCli install chromium
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Playwright Chromium with exit code $LASTEXITCODE"
    }
}

$indexPath = Join-Path $ProjectRoot "gui\index.html"
$url = ([System.Uri]$indexPath).AbsoluteUri
$script = Join-Path $ProjectRoot "tools\test-gui-browser.mjs"
$screenshot = Join-Path $outputDir "gui-smoke.png"

$env:PLAYWRIGHT_RESOLVE_FROM = $packageJson
& $Node $script $url $screenshot
if ($LASTEXITCODE -ne 0) {
    throw "Browser GUI smoke test failed with exit code $LASTEXITCODE"
}
