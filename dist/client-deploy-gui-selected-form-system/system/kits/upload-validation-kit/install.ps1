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
    Write-Warning ".env not found at $envPath; upload validation runtime settings were not checked."
}

foreach ($key in @("VALID_MATERIALS_CSV", "VALID_SLITTING_MACHINES_CSV")) {
    if ([string]::IsNullOrWhiteSpace([string]$values[$key])) {
        Write-Warning "$key is missing or empty in .env."
    }
}
