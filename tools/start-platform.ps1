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

# P3: Poll TCP until the server accepts connections or timeout expires.
function Wait-TcpReady([string]$Address, [int]$PortNum, [int]$TimeoutSecs = 10) {
    $deadline = (Get-Date).AddSeconds($TimeoutSecs)
    while ((Get-Date) -lt $deadline) {
        try {
            $c = New-Object System.Net.Sockets.TcpClient($Address, $PortNum)
            $c.Close()
            return $true
        } catch { Start-Sleep -Milliseconds 200 }
    }
    return $false
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Join-Path $PSScriptRoot ".."
}

$resolvedProjectRoot = Resolve-RequiredPath $ProjectRoot "Project root"
$entrypoint = Resolve-RequiredPath (Join-Path $resolvedProjectRoot "tools\serve-gui.cjs") "Platform server entrypoint"
Resolve-RequiredPath (Join-Path $resolvedProjectRoot "gui\index.html") "Platform GUI index" | Out-Null

# P2: Verify Node.js is reachable before doing anything else.
if (-not (Get-Command $Node -ErrorAction SilentlyContinue)) {
    throw "Node.js not found: '$Node' is not in PATH. Install Node.js or pass -Node <full-path>."
}

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

# P1: Save existing values so we can restore them when this script exits,
#     regardless of how it exits (normal, Ctrl+C, exception, early return).
$savedHost = $env:HOST
$savedPort = $env:PORT
$env:HOST = $HostAddress
$env:PORT = [string]$actualPort

try {
    if ($Background) {
        $stdoutPath = Join-Path $logsRoot "platform.out.log"
        $stderrPath = Join-Path $logsRoot "platform.err.log"
        $process = Start-Process -FilePath $Node -ArgumentList "`"$entrypoint`"" `
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
            # P3: TCP probe — open browser only after the server is actually listening.
            if (-not (Wait-TcpReady $HostAddress $actualPort 10)) {
                Write-Warning "Server did not become ready within 10 s; opening browser anyway."
            }
            Start-Process $url
        }
        return
    }

    Write-Host "Starting platform at $url"

    if ($OpenBrowser) {
        # P3: Run TCP probe in a background job so the foreground blocking call below can proceed.
        $null = Start-Job -ScriptBlock {
            param($addr, $port, $openUrl)
            $deadline = (Get-Date).AddSeconds(10)
            while ((Get-Date) -lt $deadline) {
                try {
                    $c = New-Object System.Net.Sockets.TcpClient($addr, $port)
                    $c.Close(); break
                } catch { Start-Sleep -Milliseconds 200 }
            }
            Start-Process $openUrl
        } -ArgumentList $HostAddress, $actualPort, $url
    }

    # P4: Use Start-Process -PassThru so the Node PID is captured and written to the
    #     pid file. -NoNewWindow keeps output in the current console. The pid file is
    #     cleaned up in the finally block when the process exits or Ctrl+C is pressed.
    $fgProc = Start-Process -FilePath $Node -ArgumentList "`"$entrypoint`"" `
        -WorkingDirectory $resolvedProjectRoot -NoNewWindow -PassThru
    [string]$fgProc.Id | Set-Content -LiteralPath $pidPath -Encoding UTF8
    try {
        $fgProc.WaitForExit()
    } finally {
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    }

} finally {
    # P1: Restore HOST/PORT in the caller's session.
    if ($null -eq $savedHost) { Remove-Item env:HOST -ErrorAction SilentlyContinue }
    else { $env:HOST = $savedHost }
    if ($null -eq $savedPort) { Remove-Item env:PORT -ErrorAction SilentlyContinue }
    else { $env:PORT = $savedPort }
}
