param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [string]$HostAddress = "127.0.0.1",
    [int]$BackendPort = 8000,
    [switch]$WithFrontend,
    [switch]$Background
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"
$LogPath = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $RuntimePath | Out-Null
New-Item -ItemType Directory -Force $LogPath | Out-Null

function Test-RunningPid([string]$PidPath) {
    if (-not (Test-Path $PidPath)) {
        return $false
    }

    $rawPid = (Get-Content -Raw -Encoding UTF8 $PidPath).Trim()
    if ([string]::IsNullOrWhiteSpace($rawPid)) {
        return $false
    }

    try {
        $process = Get-Process -Id ([int]$rawPid) -ErrorAction Stop
        return -not $process.HasExited
    } catch {
        return $false
    }
}

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$envPath = Join-Path $Root ".env"
$envExamplePath = Join-Path $Root ".env.example"
if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created .env from .env.example"
}

if ($Background) {
    $backendPidPath = Join-Path $RuntimePath "backend.pid"
    if (Test-RunningPid $backendPidPath) {
        throw "Backend is already running. Use scripts\status.ps1 or scripts\restart.ps1."
    }

    $backendOut = Join-Path $LogPath "backend.out.log"
    $backendErr = Join-Path $LogPath "backend.err.log"
    $backendProcess = Start-Process $Python -ArgumentList @(
        "-m", "uvicorn", "app.main:app",
        "--host", $HostAddress,
        "--port", [string]$BackendPort
    ) -WorkingDirectory (Join-Path $Root "backend") `
      -WindowStyle Hidden `
      -RedirectStandardOutput $backendOut `
      -RedirectStandardError $backendErr `
      -PassThru
    [string]$backendProcess.Id | Set-Content -Encoding UTF8 $backendPidPath

    $frontendPid = $null
    if ($WithFrontend) {
        $frontendPackage = Join-Path $Root "frontend\package.json"
        if (-not (Test-Path $frontendPackage)) {
            throw "Cannot start frontend because frontend\package.json is missing."
        }

        $frontendPidPath = Join-Path $RuntimePath "frontend.pid"
        if (Test-RunningPid $frontendPidPath) {
            throw "Frontend is already running. Use scripts\status.ps1 or scripts\restart.ps1."
        }

        $frontendOut = Join-Path $LogPath "frontend.out.log"
        $frontendErr = Join-Path $LogPath "frontend.err.log"
        $frontendProcess = Start-Process $Npm -ArgumentList @("run", "dev") `
          -WorkingDirectory (Join-Path $Root "frontend") `
          -WindowStyle Hidden `
          -RedirectStandardOutput $frontendOut `
          -RedirectStandardError $frontendErr `
          -PassThru
        [string]$frontendProcess.Id | Set-Content -Encoding UTF8 $frontendPidPath
        $frontendPid = $frontendProcess.Id
    }

    [ordered]@{
        backend = [ordered]@{
            pid = $backendProcess.Id
            url = "http://$HostAddress`:$BackendPort"
            stdout = "logs\backend.out.log"
            stderr = "logs\backend.err.log"
        }
        frontend = [ordered]@{
            requested = [bool]$WithFrontend
            pid = $frontendPid
            stdout = if ($WithFrontend) { "logs\frontend.out.log" } else { $null }
            stderr = if ($WithFrontend) { "logs\frontend.err.log" } else { $null }
        }
    } | ConvertTo-Json -Depth 10

    Write-Host "Background processes started. Use scripts\status.ps1 to inspect them."
    return
}

if ($WithFrontend) {
    $frontendPackage = Join-Path $Root "frontend\package.json"
    if (-not (Test-Path $frontendPackage)) {
        throw "Cannot start frontend because frontend\package.json is missing."
    }

    Write-Host "Starting frontend dev server in a new PowerShell process."
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location '$Root\frontend'; $Npm run dev"
    ) -WindowStyle Hidden | Out-Null
}

Write-Host "Starting backend on http://$HostAddress`:$BackendPort"
Push-Location (Join-Path $Root "backend")
try {
    & $Python -m uvicorn app.main:app --host $HostAddress --port $BackendPort
} finally {
    Pop-Location
}
