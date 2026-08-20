#Requires -Version 5.1
# Start gui-selected-form-system
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ((Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path "$ScriptDir\docker-compose.yml")) {
    docker compose -f "$ScriptDir\docker-compose.yml" up -d
    Write-Host "  Services started.  Frontend: http://localhost"
    exit 0
}

$SysRoot = "$ScriptDir\system"
if (-not (Test-Path $SysRoot)) { throw "system/ not found ??run deploy.ps1 first" }
$Python = "$SysRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "venv not found ??run deploy.ps1 first" }
New-Item -ItemType Directory -Force "$SysRoot\logs","$SysRoot\runtime" | Out-Null
$proc = Start-Process $Python `
    -ArgumentList @("-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000") `
    -WorkingDirectory "$SysRoot\backend" -WindowStyle Hidden `
    -RedirectStandardOutput "$SysRoot\logs\backend.out.log" `
    -RedirectStandardError  "$SysRoot\logs\backend.err.log" `
    -PassThru
[string]$proc.Id | Set-Content -Encoding UTF8 "$SysRoot\runtime\backend.pid"
Write-Host "  Backend started (PID=$($proc.Id)).  API: http://127.0.0.1:8000"
Write-Host "  Frontend: http://localhost  (requires nginx)"