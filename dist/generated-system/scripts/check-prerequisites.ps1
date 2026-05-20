param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..").Path,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

function Test-RelativePath([string]$Base, [string]$RelativePath) {
    return Test-Path (Join-Path $Base $RelativePath)
}

$checks = [ordered]@{
    backendApp = Test-RelativePath $Root "backend\app\main.py"
    backendRequirements = Test-RelativePath $Root "backend\requirements.txt"
    backendPyproject = Test-RelativePath $Root "backend\pyproject.toml"
    backendAlembic = Test-RelativePath $Root "backend\alembic.ini"
    frontendPackage = Test-RelativePath $Root "frontend\package.json"
    envExample = Test-RelativePath $Root ".env.example"
    dependencyManifest = Test-RelativePath $Root "dependency-manifest.json"
}

$summary = [ordered]@{
    root = $Root
    checks = $checks
    backendDependencyManifestPresent = ($checks.backendRequirements -or $checks.backendPyproject)
    frontendDependencyManifestPresent = $checks.frontendPackage
}

$summary | ConvertTo-Json -Depth 10

if (-not $checks.backendApp) {
    throw "Backend entry is missing: backend\app\main.py"
}

if ($Strict -and -not ($checks.backendRequirements -or $checks.backendPyproject)) {
    throw "Backend dependency manifest is missing. Add backend\requirements.txt or backend\pyproject.toml to the extracted source or dependency planner."
}

if ($Strict -and -not $checks.frontendPackage) {
    throw "Frontend dependency manifest is missing. Add frontend\package.json to enable frontend install/start."
}
