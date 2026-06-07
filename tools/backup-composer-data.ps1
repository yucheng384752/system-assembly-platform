param(
    [string]$BackupRoot  = (Join-Path $PSScriptRoot "..\backup"),
    [string]$DataDir     = (Join-Path $PSScriptRoot "..\data"),
    [string]$AssemblyDir = (Join-Path $PSScriptRoot "..\assembly")
)

$ErrorActionPreference = 'Stop'

$ts   = Get-Date -Format 'yyyyMMdd-HHmmss'
$dest = Join-Path $BackupRoot $ts
New-Item -ItemType Directory -Force $dest | Out-Null

$copied = 0

# Copy operations log
$opsLog = Join-Path $DataDir 'operations.jsonl'
if (Test-Path $opsLog) {
    Copy-Item $opsLog $dest
    $copied++
    Write-Host "  Copied: operations.jsonl"
}

# Copy all recipe files
$recipes = Get-ChildItem $AssemblyDir -Filter '*.recipe.json' -ErrorAction SilentlyContinue
foreach ($f in $recipes) {
    Copy-Item $f.FullName $dest
    $copied++
    Write-Host "  Copied: $($f.Name)"
}

Write-Host ""
Write-Host "Backup complete: $dest  ($copied files)"
Write-Host ""
Write-Host "Tip: for offsite DR, pass a network path:"
Write-Host "  .\backup-composer-data.ps1 -BackupRoot '\\server\share\composer-backup'"
