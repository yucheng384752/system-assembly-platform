param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ResolvedPlanPath = "assembly\mvp-resolved-plan.json",
    [string]$OutputPath = "assembly\kit-contract-report.json"
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

function Get-CapabilityName($Item) {
    if ($null -eq $Item) { return "" }
    if ($Item -is [string]) { return $Item }
    return [string]$Item.capability
}

$planPath = Join-Path $ProjectRoot $ResolvedPlanPath
$plan = Read-JsonUtf8 $planPath
$kits = @($plan.resolvedKitOrder)

$providedApi = @{}
$providedDb = @{}
$contracts = New-Object System.Collections.Generic.List[object]
$errors = New-Object System.Collections.Generic.List[string]

foreach ($kitId in $kits) {
    $contractPath = Join-Path $ProjectRoot "kits\$kitId\kit.contract.json"
    if (-not (Test-Path $contractPath)) {
        $errors.Add("Missing contract: $kitId ($contractPath)")
        continue
    }

    $contract = Read-JsonUtf8 $contractPath
    $contracts.Add($contract)

    foreach ($api in @($contract.provides.api)) {
        $cap = Get-CapabilityName $api
        if ([string]::IsNullOrWhiteSpace($cap)) { continue }
        if ($providedApi.ContainsKey($cap)) {
            $errors.Add("Duplicate API capability '$cap' provided by $($providedApi[$cap]) and $kitId")
        } else {
            $providedApi[$cap] = $kitId
        }
    }

    foreach ($db in @($contract.provides.db)) {
        $cap = Get-CapabilityName $db
        if ([string]::IsNullOrWhiteSpace($cap)) { continue }
        if (-not $providedDb.ContainsKey($cap)) {
            $providedDb[$cap] = New-Object System.Collections.Generic.List[string]
        }
        $providedDb[$cap].Add($kitId)
    }
}

foreach ($contract in $contracts) {
    $kitId = [string]$contract.kit
    foreach ($cap in @($contract.consumes.api)) {
        $name = Get-CapabilityName $cap
        if (-not [string]::IsNullOrWhiteSpace($name) -and -not $providedApi.ContainsKey($name)) {
            $errors.Add("$kitId consumes missing API capability '$name'")
        }
    }
    foreach ($cap in @($contract.consumes.db)) {
        $name = Get-CapabilityName $cap
        if (-not [string]::IsNullOrWhiteSpace($name) -and -not $providedDb.ContainsKey($name)) {
            $errors.Add("$kitId consumes missing DB capability '$name'")
        }
    }
}

$report = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    resolvedPlan = $ResolvedPlanPath
    kits = $kits
    providedApi = @($providedApi.Keys | Sort-Object)
    providedDb = @($providedDb.Keys | Sort-Object)
    errors = @($errors)
}

$reportPath = Join-Path $ProjectRoot $OutputPath
$reportDir = Split-Path -Parent $reportPath
if (-not (Test-Path $reportDir)) {
    New-Item -ItemType Directory -Force $reportDir | Out-Null
}
$report | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $reportPath

if ($errors.Count -gt 0) {
    throw "Kit contract validation failed. See $OutputPath. Errors: $($errors -join '; ')"
}

Write-Host "Kit contract validation passed: $($kits.Count) kits, $($providedApi.Count) API capabilities, $($providedDb.Count) DB capabilities"
