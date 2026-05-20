param(
    [switch]$FrontendOnly,
    [switch]$BackendOnly
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"

function Stop-ServiceByPidFile([string]$Name) {
    $pidPath = Join-Path $RuntimePath "$Name.pid"
    $result = [ordered]@{
        name = $Name
        pid = $null
        stopped = $false
        wasRunning = $false
    }

    if (-not (Test-Path $pidPath)) {
        return $result
    }

    $rawPid = (Get-Content -Raw -Encoding UTF8 $pidPath).Trim()
    if (-not [string]::IsNullOrWhiteSpace($rawPid)) {
        $result.pid = [int]$rawPid
        try {
            $process = Get-Process -Id $result.pid -ErrorAction Stop
            $result.wasRunning = $true
            Stop-Process -Id $process.Id -Force
            $result.stopped = $true
        } catch {
            $result.wasRunning = $false
        }
    }

    Remove-Item -LiteralPath $pidPath -Force
    return $result
}

$results = New-Object System.Collections.Generic.List[object]
if (-not $FrontendOnly) {
    $results.Add((Stop-ServiceByPidFile "backend"))
}
if (-not $BackendOnly) {
    $results.Add((Stop-ServiceByPidFile "frontend"))
}

[ordered]@{
    root = $Root
    results = $results.ToArray()
} | ConvertTo-Json -Depth 10
