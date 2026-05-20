param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ResolvedPlanPath = "assembly\resolved-plan.json",
    [string]$ManifestPath = "kits\form-analysis.kit-manifest.json",
    [string]$OutputDirectory = "assembly\entitlement-plan"
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

$plan = Read-JsonUtf8 (Join-Path $ProjectRoot $ResolvedPlanPath)
$manifest = Read-JsonUtf8 (Join-Path $ProjectRoot $ManifestPath)
$outputFullPath = Join-Path $ProjectRoot $OutputDirectory

if (-not (Test-Path $outputFullPath)) {
    New-Item -ItemType Directory -Force $outputFullPath | Out-Null
}

$kitMap = @{}
foreach ($kit in @($manifest.kits)) {
    $kitMap[[string]$kit.id] = $kit
}

$checks = New-Object System.Collections.Generic.List[object]
$matrix = [ordered]@{
    free = @()
    pro = @()
    enterprise = @()
}

foreach ($kitId in @($plan.resolvedKitOrder)) {
    $kit = $kitMap[[string]$kitId]
    $selectedIds = @($plan.selectedSubfeatures.$kitId)
    foreach ($subfeature in @($kit.subfeatures)) {
        if ($selectedIds.Count -gt 0 -and -not $selectedIds.Contains($subfeature.id)) {
            continue
        }
        if ($subfeature.entitlement) {
            $entry = [ordered]@{
                kit = $kitId
                subfeature = $subfeature.id
                featureKey = $subfeature.entitlement.featureKey
                requiredPlan = $subfeature.entitlement.requiredPlan
                description = $subfeature.entitlement.description
                backendCheck = "require_entitlement('$($subfeature.entitlement.featureKey)')"
                frontendCheck = "useEntitlement('$($subfeature.entitlement.featureKey)')"
            }
            $checks.Add($entry)
            $planName = [string]$subfeature.entitlement.requiredPlan
            if (-not $matrix.Contains($planName)) {
                $matrix[$planName] = @()
            }
            $matrix[$planName] += @($subfeature.entitlement.featureKey)
        }
    }
}

$entitlementPlan = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    sourceRecipe = $plan.recipe
    identityProvider = "tenant-auth-kit"
    checks = $checks.ToArray()
    planMatrix = $matrix
}

$jsonPath = Join-Path $outputFullPath "entitlement-plan.json"
$entitlementPlan | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $jsonPath

Write-Host "Entitlement plan written to $jsonPath"
