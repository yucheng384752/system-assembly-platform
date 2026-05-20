param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$generatedSystem = Join-Path $ProjectRoot "dist\generated-system"
if (-not (Test-Path $generatedSystem)) {
    & (Join-Path $ProjectRoot "tools\assemble-system.ps1") -ProjectRoot $ProjectRoot
}

& (Join-Path $ProjectRoot "tools\generate-dependency-files.ps1") `
    -ProjectRoot $ProjectRoot `
    -SystemDirectory "dist\generated-system"

$requirementsPath = Join-Path $generatedSystem "backend\requirements.txt"
$packageJsonPath = Join-Path $generatedSystem "frontend\package.json"
$planPath = Join-Path $generatedSystem "dependency-plan.json"

foreach ($path in @($requirementsPath, $packageJsonPath, $planPath)) {
    if (-not (Test-Path $path)) {
        throw "Expected dependency file was not generated: $path"
    }
}

$requirements = Get-Content -Raw -Encoding UTF8 $requirementsPath
foreach ($expected in @("fastapi", "sqlalchemy", "pydantic", "uvicorn[standard]", "asyncpg", "python-dotenv")) {
    if (-not $requirements.Contains($expected)) {
        throw "requirements.txt missing expected package: $expected"
    }
}

# Verify pinned versions: no bare package name without ==version on its own line
$requirementLines = Get-Content -Encoding UTF8 $requirementsPath
foreach ($line in $requirementLines) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
    if ($trimmed -notmatch "==") {
        throw "requirements.txt has unpinned package (missing ==version): $trimmed"
    }
}

$package = Get-Content -Raw -Encoding UTF8 $packageJsonPath | ConvertFrom-Json
foreach ($expected in @("react", "react-dom", "i18next-browser-languagedetector")) {
    if (-not ($package.dependencies.PSObject.Properties.Name -contains $expected)) {
        throw "package.json missing dependency: $expected"
    }
}
foreach ($expected in @("vite", "typescript", "@vitejs/plugin-react")) {
    if (-not ($package.devDependencies.PSObject.Properties.Name -contains $expected)) {
        throw "package.json missing devDependency: $expected"
    }
}

# Verify no "latest" version in package.json
$allVersions = @()
$allVersions += $package.dependencies.PSObject.Properties | ForEach-Object { $_.Value }
$allVersions += $package.devDependencies.PSObject.Properties | ForEach-Object { $_.Value }
foreach ($ver in $allVersions) {
    if ($ver -eq "latest") {
        throw "package.json contains unpinned 'latest' version — all packages must have explicit versions"
    }
}

Write-Host "OK dependency files"
