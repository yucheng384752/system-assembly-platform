param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$planPaths = @(
    "assembly\resolved-plan.json",
    "assembly\mvp-resolved-plan.json"
)

foreach ($relativePath in $planPaths) {
    $path = Join-Path $ProjectRoot $relativePath
    if (-not (Test-Path $path)) {
        throw "Missing resolved plan: $relativePath"
    }

    $plan = Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json

    $blankApis = @($plan.enabledApis | Where-Object { [string]::IsNullOrWhiteSpace([string]$_) })
    if ($blankApis.Count -gt 0) {
        throw "$relativePath contains blank enabledApis entries"
    }

    $duplicateApis = @(
        $plan.enabledApis |
            Group-Object |
            Where-Object { $_.Count -gt 1 } |
            ForEach-Object { $_.Name }
    )
    if ($duplicateApis.Count -gt 0) {
        throw "$relativePath contains duplicate enabledApis entries: $($duplicateApis -join ', ')"
    }

    $registrations = @($plan.backendRouterRegistrations)
    if ($registrations.Count -eq 0 -and @($plan.resolvedKitOrder).Count -gt 0) {
        throw "$relativePath has resolvedKitOrder but no backendRouterRegistrations"
    }
    foreach ($registration in $registrations) {
        if ([string]::IsNullOrWhiteSpace([string]$registration.module)) {
            throw "$relativePath has a router registration without module"
        }
        if ([string]::IsNullOrWhiteSpace([string]$registration.symbol)) {
            throw "$relativePath has a router registration without symbol for $($registration.module)"
        }
        if (-not @($registration.tags).Count) {
            throw "$relativePath has a router registration without tags for $($registration.module)"
        }
    }
}

Write-Host "OK resolved plan contracts"
