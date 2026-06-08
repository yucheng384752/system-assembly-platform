#Requires -Version 5.1
<#
.SYNOPSIS
  Build install-wizard.exe using PyInstaller.

.DESCRIPTION
  Bundles tools/install-wizard.py into a standalone Windows .exe.
  Output: dist/install-wizard.exe

.EXAMPLE
  .\tools\build-wizard-exe.ps1
  .\tools\build-wizard-exe.ps1 -OutputDir C:\release
#>
param(
    [string]$OutputDir = (Join-Path $PSScriptRoot '..\dist'),
    [string]$PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'

$wizardSrc = Join-Path $PSScriptRoot 'install-wizard.py'
if (-not (Test-Path $wizardSrc)) {
    throw "install-wizard.py not found: $wizardSrc"
}

# Check PyInstaller
try {
    & $PythonExe -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
} catch {
    Write-Host 'PyInstaller not found. Installing...'
    & $PythonExe -m pip install pyinstaller --quiet
}

# Build
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$tmpSpec = Join-Path $env:TEMP 'wizard_build'
New-Item -ItemType Directory -Force $tmpSpec | Out-Null

Write-Host 'Building install-wizard.exe...'
& $PythonExe -m PyInstaller `
    --onefile `
    --noconsole `
    --name install-wizard `
    --distpath $OutputDir `
    --workpath (Join-Path $tmpSpec 'build') `
    --specpath $tmpSpec `
    $wizardSrc

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$exePath = Join-Path $OutputDir 'install-wizard.exe'
if (Test-Path $exePath) {
    $size = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host "OK  $exePath  ($size MB)"
} else {
    throw "Build succeeded but .exe not found at $exePath"
}
