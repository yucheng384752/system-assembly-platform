param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"
$LogPath = Join-Path $Root "logs"

function Get-ServiceStatus([string]$Name) {
    $pidPath = Join-Path $RuntimePath "$Name.pid"
    $pidValue = $null
    $running = $false

    if (Test-Path $pidPath) {
        $rawPid = (Get-Content -Raw -Encoding UTF8 $pidPath).Trim()
        if (-not [string]::IsNullOrWhiteSpace($rawPid)) {
            $pidValue = [int]$rawPid
            try {
                Get-Process -Id $pidValue -ErrorAction Stop | Out-Null
                $running = $true
            } catch {
                $running = $false
            }
        }
    }

    return [ordered]@{
        pid = $pidValue
        running = $running
        pidFile = "runtime\$Name.pid"
        stdout = "logs\$Name.out.log"
        stderr = "logs\$Name.err.log"
        stdoutExists = Test-Path (Join-Path $LogPath "$Name.out.log")
        stderrExists = Test-Path (Join-Path $LogPath "$Name.err.log")
    }
}

[ordered]@{
    root = $Root
    backend = Get-ServiceStatus "backend"
    frontend = Get-ServiceStatus "frontend"
} | ConvertTo-Json -Depth 10
