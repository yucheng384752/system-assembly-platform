param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [Parameter(Mandatory)]
    [string]$ResolvedPlanPath,
    [Parameter(Mandatory)]
    [string]$SystemDirectory
)

$ErrorActionPreference = "Stop"

$plan = Get-Content -Raw -Encoding UTF8 $ResolvedPlanPath | ConvertFrom-Json

if (@($plan.resolvedKitOrder) -notcontains "generic-forms-kit") {
    Write-Host "generate-form-schema: generic-forms-kit not selected, skipping."
    return
}

$formSchemas = @($plan.formSchemas | Where-Object { $null -ne $_ })
if ($formSchemas.Count -eq 0) {
    Write-Host "generate-form-schema: no formSchemas in plan, writing empty array."
}

$outDir = Join-Path $SystemDirectory "backend\app\core"
New-Item -ItemType Directory -Force $outDir | Out-Null

$outPath = Join-Path $outDir "customer-form-schema.json"
# Write UTF-8 without BOM so Python json.loads reads it cleanly
$json = $formSchemas | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($outPath, $json, [System.Text.UTF8Encoding]::new($false))

$dataflowPath = Join-Path $outDir "customer-dataflows.json"
$dataflows = @($plan.dataflows | Where-Object { $null -ne $_ })
$dataflowJson = if ($dataflows.Count -eq 0) { "[]" } else { $dataflows | ConvertTo-Json -Depth 20 }
[System.IO.File]::WriteAllText($dataflowPath, $dataflowJson, [System.Text.UTF8Encoding]::new($false))

Write-Host "generate-form-schema: wrote $($formSchemas.Count) form(s) to $outPath"
Write-Host "generate-form-schema: wrote dataflows to $dataflowPath"
