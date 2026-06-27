<#
.SYNOPSIS
Starts the Form System Kit Composer platform GUI.

.DESCRIPTION
The platform is currently served by the Node entrypoint tools/serve-gui.cjs.
This wrapper gives the project a stable PowerShell startup command with port
selection, background mode, pid files, logs, and optional browser opening.

.EXAMPLE
.\tools\start-platform.ps1

.EXAMPLE
.\tools\start-platform.ps1 -Background

.EXAMPLE
.\tools\start-platform.ps1 -Port 4174 -NoAutoPort
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$Node = "node",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 4173,
    [switch]$Background,
    [switch]$NoAutoPort,
    [switch]$OpenBrowser = $true,
    [switch]$Restart,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"

function Resolve-RequiredPath([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Test-TcpPortInUse([string]$Address, [int]$PortNumber) {
    $listener = $null
    try {
        $ipAddress = [System.Net.IPAddress]::Parse($Address)
        $listener = [System.Net.Sockets.TcpListener]::new($ipAddress, $PortNumber)
        $listener.Start()
        return $false
    } catch {
        return $true
    } finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

function Get-AvailablePort([string]$Address, [int]$PreferredPort) {
    if ($NoAutoPort) {
        if (Test-TcpPortInUse $Address $PreferredPort) {
            throw "Port $PreferredPort is already in use on $Address."
        }
        return $PreferredPort
    }

    for ($candidate = $PreferredPort; $candidate -lt ($PreferredPort + 50); $candidate++) {
        if (-not (Test-TcpPortInUse $Address $candidate)) {
            return $candidate
        }
    }
    throw "No available port found from $PreferredPort to $($PreferredPort + 49) on $Address."
}

function Test-RunningPid([string]$PidPath) {
    if (-not (Test-Path -LiteralPath $PidPath)) {
        return $false
    }

    $rawPid = (Get-Content -LiteralPath $PidPath -Raw -Encoding UTF8).Trim()
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

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Join-Path $PSScriptRoot ".."
}

$resolvedProjectRoot = Resolve-RequiredPath $ProjectRoot "Project root"
$entrypoint = Resolve-RequiredPath (Join-Path $resolvedProjectRoot "tools\serve-gui.cjs") "Platform server entrypoint"
Resolve-RequiredPath (Join-Path $resolvedProjectRoot "gui\index.html") "Platform GUI index" | Out-Null

$runtimeRoot = Join-Path $resolvedProjectRoot "runtime"
$logsRoot = Join-Path $resolvedProjectRoot "logs"
$pidPath = Join-Path $runtimeRoot "platform.pid"
$actualPort = Get-AvailablePort $HostAddress $Port
$url = "http://$HostAddress`:$actualPort/"

$plan = [ordered]@{
    projectRoot = $resolvedProjectRoot
    entrypoint = $entrypoint
    host = $HostAddress
    requestedPort = $Port
    actualPort = $actualPort
    url = $url
    background = [bool]$Background
    pidFile = "runtime\platform.pid"
    stdout = "logs\platform.out.log"
    stderr = "logs\platform.err.log"
}

Write-Host ($plan | ConvertTo-Json -Depth 10)

if ($PlanOnly) {
    Write-Host "PlanOnly was set; platform server was not started."
    return
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null

if (Test-RunningPid $pidPath) {
    $existingPid = (Get-Content -LiteralPath $pidPath -Raw -Encoding UTF8).Trim()
    if ($Restart) {
        Write-Host "Stopping existing platform instance (PID $existingPid)..."
        try {
            Stop-Process -Id ([int]$existingPid) -Force -ErrorAction SilentlyContinue
        } catch {}
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 800
        Write-Host "Existing instance stopped."
    } elseif ($Background) {
        throw "Platform already running (PID $existingPid). Use -Restart to stop and restart, or stop it manually."
    }
}

$env:HOST = $HostAddress
$env:PORT = [string]$actualPort

if ($Background) {
    $stdoutPath = Join-Path $logsRoot "platform.out.log"
    $stderrPath = Join-Path $logsRoot "platform.err.log"
    $process = Start-Process -FilePath $Node -ArgumentList @($entrypoint) `
        -WorkingDirectory $resolvedProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru
    [string]$process.Id | Set-Content -LiteralPath $pidPath -Encoding UTF8

    [ordered]@{
        pid = $process.Id
        url = $url
        stdout = $stdoutPath
        stderr = $stderrPath
    } | ConvertTo-Json -Depth 10

    if ($OpenBrowser) {
        Start-Sleep -Milliseconds 1500
        Start-Process $url | Out-Null
    }
    return
}

Write-Host "Starting platform at $url"

if ($OpenBrowser) {
    # Open browser after server is ready (1.5s delay via background job to avoid race condition)
    $openUrl = $url
    $null = Start-Job -ScriptBlock {
        Start-Sleep -Milliseconds 1500
        Start-Process $using:openUrl
    }
}

& $Node $entrypoint
