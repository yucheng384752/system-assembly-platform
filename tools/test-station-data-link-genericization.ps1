param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

function Read-Json([string]$Path) {
    Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
}

function Write-Json([string]$Path, [object]$Value) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    $Value | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 -LiteralPath $Path
}

$manifest = Read-Json (Join-Path $ProjectRoot "kits\form-analysis.kit-manifest.json")
$kit = $manifest.kits | Where-Object id -eq "station-data-link-kit"
$adapter = $kit.subfeatures | Where-Object id -eq "p123-compatibility-adapter"

if ($null -eq $adapter -or $false -ne $adapter.defaultSelected) {
    throw "P1/P2/P3 compatibility adapter must exist and default to disabled"
}

$legacyPattern = '(^|[\\/])p[123]_|P[123](Record|Item)|production_date_extractor'
$coreValues = @($kit.backend.models) + @($kit.backend.services) + @($kit.database.models)
if (@($coreValues | Where-Object { [string]$_ -match $legacyPattern }).Count) {
    throw "station-data-link-kit core still contains P1/P2/P3 contributions"
}

$adapterValues = @($adapter.contributions.backend.models) + @($adapter.contributions.backend.services) + @($adapter.contributions.database.models)
if (-not @($adapterValues | Where-Object { [string]$_ -match 'P1Record|p1_record' }).Count) {
    throw "Compatibility adapter does not contribute P1 legacy models"
}

$buildRelative = "build\station-data-link-genericization"
$buildRoot = Join-Path $ProjectRoot $buildRelative
$genericRecipePath = Join-Path $buildRoot "generic-only.recipe.json"
$genericPlanPath = Join-Path $buildRoot "generic-only.resolved-plan.json"
$legacyRecipePath = Join-Path $buildRoot "legacy-on.recipe.json"
$legacyPlanPath = Join-Path $buildRoot "legacy-on.resolved-plan.json"

$genericRecipe = Read-Json (Join-Path $ProjectRoot "assembly\form-analysis-original.recipe.json")
$genericRecipe.name = "station-data-link-generic-only-test"
$genericRecipe.selectedSubfeatures.'station-data-link-kit' = @(
    "station-data-model",
    "new-station-definition",
    "lot-normalization",
    "product-id-generation",
    "generic-record"
)
Write-Json $genericRecipePath $genericRecipe

& (Join-Path $ProjectRoot "tools\resolve-recipe.ps1") `
    -ProjectRoot $ProjectRoot `
    -RecipePath "$buildRelative\generic-only.recipe.json" `
    -OutputPath "$buildRelative\generic-only.resolved-plan.json" | Out-Null

$genericPlan = Read-Json $genericPlanPath
$genericValues = @($genericPlan.requiredModels) + @($genericPlan.backendSources)
if (@($genericValues | Where-Object { [string]$_ -match $legacyPattern }).Count) {
    throw "Generic-only resolved plan contains P1/P2/P3 legacy contributions"
}
if ($genericPlan.featureFlags.LEGACY_TABLE_CODES_CSV) {
    throw "Generic-only resolved plan exposes legacy table codes"
}
if (@($genericPlan.backendRouterRegistrations.module).Contains("app.api.routes_import")) {
    throw "Generic-only resolved plan contains the legacy import router"
}
foreach ($model in @("Station", "StationSchema", "StationLink", "GenericRecord", "GenericRecordItem")) {
    if (-not @($genericPlan.requiredModels).Contains($model)) {
        throw "Generic-only resolved plan is missing canonical model: $model"
    }
}

$legacyRecipe = Read-Json (Join-Path $ProjectRoot "assembly\form-analysis-original.recipe.json")
$legacyRecipe.name = "station-data-link-legacy-on-test"
if (-not @($legacyRecipe.selectedSubfeatures.'station-data-link-kit').Contains("p123-compatibility-adapter")) {
    $legacyRecipe.selectedSubfeatures.'station-data-link-kit' += "p123-compatibility-adapter"
}
Write-Json $legacyRecipePath $legacyRecipe

& (Join-Path $ProjectRoot "tools\resolve-recipe.ps1") `
    -ProjectRoot $ProjectRoot `
    -RecipePath "$buildRelative\legacy-on.recipe.json" `
    -OutputPath "$buildRelative\legacy-on.resolved-plan.json" | Out-Null

$legacyPlan = Read-Json $legacyPlanPath
foreach ($model in @("P1Record", "P2Record", "P2ItemV2", "P3Record", "P3ItemV2")) {
    if (-not @($legacyPlan.requiredModels).Contains($model)) {
        throw "Legacy-on resolved plan is missing compatibility model: $model"
    }
}
if (-not @($legacyPlan.backendSources).Contains("backend/app/services/production_date_extractor.py")) {
    throw "Legacy-on resolved plan is missing compatibility date extractor"
}
if ($legacyPlan.featureFlags.LEGACY_TABLE_CODES_CSV -ne "P1,P2,P3") {
    throw "Legacy-on resolved plan is missing compatibility table-code config"
}
if (-not @($legacyPlan.backendRouterRegistrations.module).Contains("app.api.routes_import")) {
    throw "Legacy-on resolved plan is missing the compatibility import router"
}

$genericSystemRelative = "$buildRelative\assembled-generic"
$legacySystemRelative = "$buildRelative\assembled-legacy"
& (Join-Path $ProjectRoot "tools\assemble-system.ps1") `
    -ProjectRoot $ProjectRoot `
    -ResolvedPlanPath "$buildRelative\generic-only.resolved-plan.json" `
    -OutputDirectory $genericSystemRelative `
    -SkipFrontendBuild | Out-Null

$genericSystemRoot = Join-Path $ProjectRoot $genericSystemRelative
foreach ($relativePath in @(
    "backend\app\api\routes_import.py",
    "backend\app\models\record.py",
    "backend\app\models\p1_record.py",
    "backend\app\models\p2_record.py",
    "backend\app\models\p3_record.py",
    "backend\app\services\production_date_extractor.py"
)) {
    if (Test-Path (Join-Path $genericSystemRoot $relativePath)) {
        throw "Generic-only assembly contains legacy file: $relativePath"
    }
}
$genericInit = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $genericSystemRoot "backend\app\models\__init__.py")
if ($genericInit -match 'P[123](Record|Item)|DataType|from \..+\. import') {
    throw "Generic-only generated model exports contain legacy or invalid imports"
}
$genericEnv = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $genericSystemRoot ".env.example")
if ($genericEnv -notmatch '(?m)^USE_GENERIC_SCHEMA=true$' -or $genericEnv -notmatch '(?m)^LEGACY_TABLE_CODES_CSV=$') {
    throw "Generic-only environment does not select generic storage exclusively"
}

& (Join-Path $ProjectRoot "tools\assemble-system.ps1") `
    -ProjectRoot $ProjectRoot `
    -ResolvedPlanPath "$buildRelative\legacy-on.resolved-plan.json" `
    -OutputDirectory $legacySystemRelative `
    -SkipFrontendBuild | Out-Null

$legacySystemRoot = Join-Path $ProjectRoot $legacySystemRelative
foreach ($relativePath in @(
    "backend\app\api\routes_import.py",
    "backend\app\models\record.py",
    "backend\app\models\p1_record.py",
    "backend\app\models\p2_record.py",
    "backend\app\models\p3_record.py",
    "backend\app\services\production_date_extractor.py"
)) {
    if (-not (Test-Path (Join-Path $legacySystemRoot $relativePath))) {
        throw "Legacy-on assembly is missing compatibility file: $relativePath"
    }
}
$legacyEnv = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $legacySystemRoot ".env.example")
if ($legacyEnv -notmatch '(?m)^LEGACY_TABLE_CODES_CSV=P1,P2,P3$') {
    throw "Legacy-on environment is missing compatibility table codes"
}

$sourceRoot = Join-Path $ProjectRoot "generated\mvp-import-flow\form-analysis-server"
$phase2Checks = @(
    @{ Path = "frontend\src\pages\upload\uploadTypes.ts"; Forbidden = '"P1" \| "P2" \| "P3"' },
    @{ Path = "frontend\src\pages\upload\uploadFileUtils.ts"; Forbidden = 'startsWith\("P[123]_' },
    @{ Path = "frontend\src\pages\upload\uploadFileAddUtils.ts"; Forbidden = 'type === "P1"|type === "P2"' },
    @{ Path = "frontend\src\pages\upload\UploadedFileCard.tsx"; Forbidden = "file\.type === 'P[123]'" },
    @{ Path = "backend\app\api\routes_upload.py"; Forbidden = 'token in \{"P1", "P2", "P3"\}' },
    @{ Path = "backend\app\services\pdf_conversion.py"; Forbidden = 'table_type == "P2"' },
    @{ Path = "backend\app\main.py"; Forbidden = 'for code in \("P1", "P2", "P3"\)' }
)
foreach ($check in $phase2Checks) {
    $content = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $sourceRoot $check.Path)
    if ($content -match $check.Forbidden) {
        throw "Phase 2 caller remains hardcoded: $($check.Path)"
    }
}

$importV2 = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $sourceRoot "backend\app\services\import_v2.py")
foreach ($required in @("_station_schema_validation_rules", "if schema_driven:", "if generic_rows_list:")) {
    if ($importV2 -notmatch [regex]::Escape($required)) {
        throw "Import V2 is missing schema-driven behavior: $required"
    }
}

if ($adapter.contributions.config.PDF_WINDER_TABLE_CODES_CSV -ne "P2") {
    throw "Compatibility adapter is missing PDF winder enrichment metadata"
}

Write-Host "OK station-data-link genericization resolver contract"
