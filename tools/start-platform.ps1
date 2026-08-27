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

function Repair-ProcessPathEnvironment {
    $envVars = [System.Environment]::GetEnvironmentVariables("Process")
    $pathKeys = @()
    foreach ($key in $envVars.Keys) {
        if ([string]$key -ieq "Path") {
            $pathKeys += [string]$key
        }
    }

    if ($pathKeys.Count -le 1) {
        return
    }

    $pathParts = New-Object System.Collections.Generic.List[string]
    foreach ($key in $pathKeys) {
        foreach ($part in ([string]$envVars[$key] -split ';')) {
            if (-not [string]::IsNullOrWhiteSpace($part) -and -not $pathParts.Contains($part)) {
                $pathParts.Add($part) | Out-Null
            }
        }
    }
    $preferredValue = ($pathParts -join ';')
    foreach ($key in $pathKeys) {
        [System.Environment]::SetEnvironmentVariable($key, $null, "Process")
    }
    [System.Environment]::SetEnvironmentVariable("Path", $preferredValue, "Process")
}

function New-NodeBootstrapArguments(
    [string]$LauncherPath,
    [string]$EntrypointPath,
    [string]$Address,
    [int]$PortNumber,
    [string]$StdoutPath = "",
    [string]$StderrPath = ""
) {
    $args = New-Object System.Collections.Generic.List[string]
    foreach ($arg in @($LauncherPath, $EntrypointPath, $Address, [string]$PortNumber)) {
        $args.Add('"' + $arg.Replace('"', '\"') + '"') | Out-Null
    }
    if (-not [string]::IsNullOrWhiteSpace($StdoutPath) -and -not [string]::IsNullOrWhiteSpace($StderrPath)) {
        $args.Add('"' + $StdoutPath.Replace('"', '\"') + '"') | Out-Null
        $args.Add('"' + $StderrPath.Replace('"', '\"') + '"') | Out-Null
    }
    return ($args -join " ")
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

# Returns the PID of the process listening on the given port, or $null.
# Uses netstat so it catches any process regardless of whether the PID file knows about it.
function Get-PortOwnerPid([int]$PortNumber) {
    $match = netstat -ano 2>$null |
        Select-String "LISTENING" |
        Where-Object { $_.Line -match ":$PortNumber\s" } |
        Select-Object -First 1
    if (-not $match) { return $null }
    $parts = $match.Line.Trim() -split '\s+'
    $ownerPid = [int]$parts[-1]
    if ($ownerPid -gt 0) {
        return $ownerPid
    }
    return $null
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
$launcher = Resolve-RequiredPath (Join-Path $resolvedProjectRoot "tools\serve-gui-launcher.cjs") "Platform server launcher"
Resolve-RequiredPath (Join-Path $resolvedProjectRoot "gui\index.html") "Platform GUI index" | Out-Null

Repair-ProcessPathEnvironment

# P2: Verify Node.js is reachable before doing anything else.
$nodeCommand = Get-Command $Node -ErrorAction SilentlyContinue
if (-not $nodeCommand) {
    throw "Node.js not found: '$Node' is not in PATH. Install Node.js or pass -Node <full-path>."
}
$nodeExecutable = $nodeCommand.Source

$runtimeRoot = Join-Path $resolvedProjectRoot "runtime"
$logsRoot = Join-Path $resolvedProjectRoot "logs"
$pidPath = Join-Path $runtimeRoot "platform.pid"

# Clean up stale PID file (process dead but file still exists).
if ((Test-Path -LiteralPath $pidPath) -and -not (Test-RunningPid $pidPath)) {
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
}

# Detect orphan: any process listening on the preferred port that is NOT tracked
# by the PID file (e.g. started manually with `node tools/serve-gui.cjs`).
$orphanPid = Get-PortOwnerPid $Port
if ($orphanPid) {
    $pidFileEntry = if (Test-Path -LiteralPath $pidPath) {
        (Get-Content -LiteralPath $pidPath -Raw -Encoding UTF8).Trim()
    } else { "" }

    if ($pidFileEntry -ne [string]$orphanPid) {
        if ($Restart) {
            Write-Host "Port $Port is occupied by untracked PID $orphanPid — stopping orphan..."
            Stop-Process -Id $orphanPid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 600
            Write-Host "Orphan stopped."
        } else {
            Write-Warning "Port $Port is occupied by PID $orphanPid which is not tracked by the PID file."
            Write-Warning "This orphan will remain running alongside the new server on a different port."
            Write-Warning "Use -Restart to stop it automatically before starting."
        }
    }
}

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
        $nodeArgs = New-NodeBootstrapArguments $launcher $entrypoint $HostAddress $actualPort $stdoutPath $stderrPath
        $process = Start-Process -FilePath $nodeExecutable -ArgumentList $nodeArgs `
            -WorkingDirectory $resolvedProjectRoot `
            -WindowStyle Hidden `
            -PassThru
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) {
            throw "Platform server exited immediately (exit $($process.ExitCode)). Node: $nodeExecutable Args: $nodeArgs"
        }
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
    $nodeArgs = New-NodeBootstrapArguments $launcher $entrypoint $HostAddress $actualPort
    $fgProc = Start-Process -FilePath $nodeExecutable -ArgumentList $nodeArgs `
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
