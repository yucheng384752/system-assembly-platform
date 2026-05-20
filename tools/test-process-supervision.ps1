param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$GeneratedSystemDirectory = "dist\generated-system"
)

$ErrorActionPreference = "Stop"

$root = Join-Path $ProjectRoot $GeneratedSystemDirectory
if (-not (Test-Path $root)) {
    & (Join-Path $ProjectRoot "tools\assemble-system.ps1") -ProjectRoot $ProjectRoot
}

$requiredPaths = @(
    "scripts\start.ps1",
    "scripts\status.ps1",
    "scripts\stop.ps1",
    "scripts\restart.ps1"
)

foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path (Join-Path $root $relativePath))) {
        throw "Missing process supervision path: $relativePath"
    }
}

$startScript = Get-Content -Raw -Encoding UTF8 (Join-Path $root "scripts\start.ps1")
$statusScript = Get-Content -Raw -Encoding UTF8 (Join-Path $root "scripts\status.ps1")
$stopScript = Get-Content -Raw -Encoding UTF8 (Join-Path $root "scripts\stop.ps1")
$restartScript = Get-Content -Raw -Encoding UTF8 (Join-Path $root "scripts\restart.ps1")

$expectedStartPatterns = @(
    '[switch]$Background',
    'runtime',
    'logs',
    'backend.pid',
    'RedirectStandardOutput',
    'RedirectStandardError',
    'Start-Process'
)

foreach ($pattern in $expectedStartPatterns) {
    if (-not $startScript.Contains($pattern)) {
        throw "scripts\start.ps1 is missing expected process supervision pattern: $pattern"
    }
}

if ($statusScript -notmatch "Get-Process" -or $statusScript -notmatch "ConvertTo-Json") {
    throw "scripts\status.ps1 must inspect pid files and emit JSON."
}

if ($stopScript -notmatch "Stop-Process" -or $stopScript -notmatch "Remove-Item") {
    throw "scripts\stop.ps1 must stop processes and remove pid files."
}

if ($restartScript -notmatch "stop\.ps1" -or $restartScript -notmatch "start\.ps1" -or $restartScript -notmatch "\-Background") {
    throw "scripts\restart.ps1 must stop then start in background mode."
}

$statusJson = & (Join-Path $root "scripts\status.ps1") | ConvertFrom-Json
if ($null -eq $statusJson.backend -or $null -eq $statusJson.frontend) {
    throw "scripts\status.ps1 did not emit backend/frontend status."
}

& (Join-Path $root "scripts\stop.ps1") | Out-Host

Write-Host "OK process supervision"
