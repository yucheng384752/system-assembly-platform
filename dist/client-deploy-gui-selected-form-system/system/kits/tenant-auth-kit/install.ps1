param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
)

$ErrorActionPreference = "Stop"

$envPath = Join-Path $Root ".env"
$values = @{}
if (Test-Path $envPath) {
    Get-Content -Encoding UTF8 $envPath | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and $_ -notmatch '^\s*#') {
            $values[$Matches[1]] = $Matches[2]
        }
    }
} else {
    throw ".env not found at $envPath; SECRET_KEY is required for tenant auth."
}

if ([string]::IsNullOrWhiteSpace([string]$values.SECRET_KEY)) {
    throw "SECRET_KEY is missing or empty in .env."
}
if ([string]::IsNullOrWhiteSpace([string]$values.AUTH_MODE)) {
    Write-Warning "AUTH_MODE is missing or empty in .env."
}
