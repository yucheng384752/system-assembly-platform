param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$PackageRoot = "dist\client-deploy-gui-selected-form-system"
)

$ErrorActionPreference = "Stop"

$root = Join-Path $ProjectRoot $PackageRoot
if (-not (Test-Path $root)) {
    throw "Client deploy package not found: $root"
}

$required = @(
    "deploy.sh",
    "deploy-offline.sh",
    "deploy-online.sh",
    "deploy.ps1",
    "deploy-offline.ps1",
    "deploy-online.ps1"
)

foreach ($relative in $required) {
    $path = Join-Path $root $relative
    if (-not (Test-Path $path)) {
        throw "Missing deploy variant: $relative"
    }
}

foreach ($relative in @("deploy.ps1", "deploy-offline.ps1", "deploy-online.ps1")) {
    $path = Join-Path $root $relative
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors -and $errors.Count -gt 0) {
        throw "PowerShell parse failed for ${relative}: $($errors[0].Message)"
    }
}

$offlineFiles = @("deploy.sh", "deploy-offline.sh", "deploy.ps1", "deploy-offline.ps1")
$forbiddenOffline = @("HIBA_", "/api/hiba/nodes/register", "HibaDashboard", "Configure-HibaNode")
foreach ($relative in $offlineFiles) {
    $content = Get-Content -Raw -Encoding UTF8 (Join-Path $root $relative)
    foreach ($needle in $forbiddenOffline) {
        if ($content.Contains($needle)) {
            throw "Offline deploy script $relative contains forbidden online marker: $needle"
        }
    }
}

$onlineExpectations = @{
    "deploy-online.sh" = @(
        "HIBA_NODE_ID",
        "HIBA_DASHBOARD_URL",
        "HIBA_DASHBOARD_TOKEN",
        "HIBA_CALLBACK_ENABLED",
        "/api/hiba/nodes/register",
        "chmod 600",
        "urllib.request.urlopen"
    )
    "deploy-online.ps1" = @(
        "HibaNodeId",
        "HIBA_DASHBOARD_URL",
        "HIBA_DASHBOARD_TOKEN",
        "HIBA_CALLBACK_ENABLED",
        "/api/hiba/nodes/register",
        "Protect-EnvFile",
        "Invoke-WebRequest"
    )
}

foreach ($entry in $onlineExpectations.GetEnumerator()) {
    $content = Get-Content -Raw -Encoding UTF8 (Join-Path $root $entry.Key)
    foreach ($needle in $entry.Value) {
        if (-not $content.Contains($needle)) {
            throw "Online deploy script $($entry.Key) is missing expected marker: $needle"
        }
    }
}

Write-Host "OK client deploy online/offline variants"
