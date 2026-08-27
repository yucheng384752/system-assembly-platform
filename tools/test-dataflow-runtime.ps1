param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$routes = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "kits\generic-forms-kit\src\backend\app\api\routes_generic_forms.py")
$trace = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "kits\query-traceability-kit\src\backend\app\api\routes_query_v2.py")
$seed = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "kits\query-traceability-kit\src\backend\app\core\seed_stations.py")
$generator = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "tools\generate-form-schema.ps1")

@(
    '@router.get("/dataflows/links"',
    '@router.post("/dataflows/links"',
    '@router.put("/dataflows/links"',
    '@router.delete("/dataflows/links/{from_code}/{to_code}"',
    'def _would_create_cycle',
    'sql_delete(StationLink)'
) | ForEach-Object {
    if (-not $routes.Contains($_)) { throw "Runtime dataflow API missing contract: $_" }
}

if (-not $trace.Contains('flow_code: str = "default"') -or -not $trace.Contains('flowCodes')) {
    throw "Trace API is not dataflow-aware"
}
if (-not $seed.Contains('customer-dataflows.json') -or -not $seed.Contains('keyMappings')) {
    throw "Generated dataflows are not seeded"
}
if (-not $generator.Contains('customer-dataflows.json')) {
    throw "Resolved plan does not emit customer dataflows"
}

Write-Host "OK dataflow runtime contracts"
