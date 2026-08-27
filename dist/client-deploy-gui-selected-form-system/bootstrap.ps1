#Requires -Version 5.1
# gui-selected-form-system — bootstrap: ensure Python 3 + pip, then launch the install wizard.
# Run this FIRST on a fresh VM that may not have Python installed.
#   .\bootstrap.ps1
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-Python { [bool](Get-Command python -ErrorAction SilentlyContinue) }

function Install-Python {
    # 1) Offline: bundled installer in installers\ (drop .exe/.msi there before transfer)
    $inst = Get-ChildItem -Path "$ScriptDir\installers" -Include *.exe,*.msi -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($inst) {
        Write-Host "  Installing Python from bundled $($inst.Name)..."
        if ($inst.Extension -eq ".msi") {
            Start-Process msiexec.exe -ArgumentList "/i `"$($inst.FullName)`" /quiet InstallAllUsers=1 PrependPath=1" -Wait
        } else {
            Start-Process $inst.FullName -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
        }
        return
    }
    # 2) Online: winget
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  Installing Python via winget..."
        winget install -e --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
        return
    }
    throw "No bundled installer in installers\ and winget unavailable. Install Python 3.11+ from https://www.python.org/downloads/"
}

if (-not (Test-Python)) {
    Write-Host "  Python not found."
    Install-Python
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    if (-not (Test-Python)) {
        throw "Python installed but not yet on PATH. Close and reopen PowerShell, then re-run bootstrap.ps1."
    }
}
Write-Host "  Python: $(python --version 2>&1)"

python -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  pip not found — bootstrapping with ensurepip..."
    python -m ensurepip --upgrade
}

Write-Host ""
Write-Host "  Launching install wizard..."
python "$ScriptDir\install-wizard.py"