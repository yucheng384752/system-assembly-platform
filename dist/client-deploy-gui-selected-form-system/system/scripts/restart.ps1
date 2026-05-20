param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [string]$HostAddress = "127.0.0.1",
    [int]$BackendPort = 8000,
    [switch]$WithFrontend
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "stop.ps1") | Out-Host
& (Join-Path $PSScriptRoot "start.ps1") `
    -Python $Python `
    -Npm $Npm `
    -HostAddress $HostAddress `
    -BackendPort $BackendPort `
    -WithFrontend:$WithFrontend `
    -Background
