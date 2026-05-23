param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

& (Join-Path $ProjectRoot "tools\generate-db-plan.ps1") -ProjectRoot $ProjectRoot

$planPath = Join-Path $ProjectRoot "assembly\db-plan\db-assembly-plan.json"
$inferencePath = Join-Path $ProjectRoot "assembly\db-plan\daihui-schema-inference.json"
$baselinePath = Join-Path $ProjectRoot "assembly\baselines\daihui-form-schema.baseline.json"

if (-not (Test-Path $baselinePath)) { throw "Missing Daihui schema baseline: $baselinePath" }
if (-not (Test-Path $planPath)) { throw "Missing DB assembly plan: $planPath" }
if (-not (Test-Path $inferencePath)) { throw "Missing Daihui schema inference report: $inferencePath" }

$baseline = Get-Content -Raw -Encoding UTF8 $baselinePath | ConvertFrom-Json
$plan = Get-Content -Raw -Encoding UTF8 $planPath | ConvertFrom-Json
$inference = Get-Content -Raw -Encoding UTF8 $inferencePath | ConvertFrom-Json

if ($baseline.packId -ne "daihui-form-schema") { throw "Unexpected Daihui packId: $($baseline.packId)" }
if ($baseline.strategy -ne "hybrid-generic") { throw "Unexpected Daihui strategy: $($baseline.strategy)" }
if (@($baseline.forms).Count -ne 5) { throw "Daihui baseline should define 5 forms" }

$domainPack = @($plan.schemaContracts.domainPacks) | Where-Object { $_.packId -eq "daihui-form-schema" } | Select-Object -First 1
if ($null -eq $domainPack) { throw "DB plan does not reference Daihui domain schema pack" }
if (@($plan.schemaVersions).Count -ne 5) { throw "DB plan should produce 5 Daihui schema versions" }
if (@($plan.seedData.formDefinitions).Count -ne 5) { throw "DB plan should produce 5 Daihui form definitions" }
if (@($plan.relationships).Count -lt 3) { throw "DB plan should include Daihui ER relationships" }
if (@($plan.indexes).Count -lt 3) { throw "DB plan should include Daihui generic-record indexes" }

if (@($inference.forms).Count -ne 5) { throw "Daihui inference report should include 5 forms" }
foreach ($form in @($inference.forms)) {
    if ($form.rowCount -lt 1) { throw "Daihui sample has no rows: $($form.sampleFile)" }
    if ([string]::IsNullOrWhiteSpace([string]$form.headerFingerprint)) {
        throw "Daihui sample has no header fingerprint: $($form.sampleFile)"
    }
}

Write-Host "OK Daihui schema plan"
