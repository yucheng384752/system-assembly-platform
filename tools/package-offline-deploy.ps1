param(
    [string]$ProjectRoot  = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$RecipeName   = '',
    [string]$PackageName  = 'form-manager-system',
    [string]$OutputDir    = 'dist'
)

$ErrorActionPreference = 'Stop'

Write-Host '=================================================='
Write-Host "  Form System offline package builder"
Write-Host "  PackageName : $PackageName"
Write-Host '=================================================='
Write-Host ''

# Step 1: build the online deploy package
Write-Host '>> Step 1/3  Building client-deploy package...'
$pkgArgs = @(
    '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $PSScriptRoot 'package-client-deploy.ps1'),
    '-ProjectRoot', $ProjectRoot,
    '-PackageName', $PackageName,
    '-OutputDir', $OutputDir,
    '-SkipZip'
)
if ($RecipeName) { $pkgArgs += '-RecipeName', $RecipeName }
& powershell @pkgArgs
if ($LASTEXITCODE -ne 0) { throw "package-client-deploy.ps1 failed (exit $LASTEXITCODE)" }

$deployDir = Join-Path $ProjectRoot $OutputDir ('client-deploy-' + $PackageName)
$systemDir  = Join-Path $deployDir 'system'

Write-Host ''
Write-Host '>> Step 2/3  Preparing offline dependencies (pip wheels + npm cache)...'
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'prepare-offline.ps1') `
    -SystemDir $systemDir
if ($LASTEXITCODE -ne 0) { throw "prepare-offline.ps1 failed (exit $LASTEXITCODE)" }

Write-Host ''
Write-Host '>> Step 3/3  Bundling Docker images + system into offline archive...'
$offlineBundleRel = Join-Path $OutputDir ('offline-bundle-' + $PackageName)
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'bundle-offline.ps1') `
    -DeployDir (Join-Path $OutputDir ('client-deploy-' + $PackageName)) `
    -OutputDir $offlineBundleRel
if ($LASTEXITCODE -ne 0) { throw "bundle-offline.ps1 failed (exit $LASTEXITCODE)" }

# Create final ZIP
$bundlePath = Join-Path $ProjectRoot $offlineBundleRel
$zipPath    = Join-Path $ProjectRoot $OutputDir ($PackageName + '-offline.zip')
Write-Host ''
Write-Host ">> Compressing offline bundle -> $zipPath"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $bundlePath '*') -DestinationPath $zipPath -Force
Write-Host ''
Write-Host "  Offline package : $zipPath"
Write-Host "  Size            : $([math]::Round((Get-Item $zipPath).Length / 1MB, 1)) MB"
Write-Host ''
Write-Host '=================================================='
Write-Host "  Done.  Deliver $($PackageName)-offline.zip to target machine."
Write-Host '  Run:   bash install-offline.sh  (Linux)'
Write-Host '         .\install-offline.ps1    (Windows)'
Write-Host '=================================================='
