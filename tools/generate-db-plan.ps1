param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ResolvedPlanPath = "assembly\resolved-plan.json",
    [string]$ManifestPath = "kits\form-analysis.kit-manifest.json",
    [string]$OutputDirectory = "assembly\db-plan"
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

$models = New-Object System.Collections.Generic.List[string]
$migrations = New-Object System.Collections.Generic.List[string]
$modelFiles = New-Object System.Collections.Generic.List[string]
$seedRequirements = New-Object System.Collections.Generic.List[object]
$envVars = [ordered]@{
    DATABASE_URL = "required"
}

foreach ($kitId in @($plan.resolvedKitOrder)) {
    $kit = $kitMap[[string]$kitId]
    foreach ($model in @($kit.database.models)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$model) -and -not $models.Contains([string]$model)) {
            $models.Add([string]$model)
        }
    }
    foreach ($migration in @($kit.database.migrations)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$migration) -and -not $migrations.Contains([string]$migration)) {
            $migrations.Add([string]$migration)
        }
    }
    foreach ($modelFile in @($kit.backend.models)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$modelFile) -and -not $modelFiles.Contains([string]$modelFile)) {
            $modelFiles.Add([string]$modelFile)
        }
    }
    if ($kit.id -eq "station-admin-kit") {
        $seedRequirements.Add([ordered]@{
            kit = $kit.id
            name = "generic-station-definitions"
            requiredWhen = "USE_GENERIC_SCHEMA"
        })
    }
}

$dbPlan = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    sourceRecipe = $plan.recipe
    engine = $plan.database.engine
    connectionOwner = "platform-core-kit"
    envVars = $envVars
    models = $models.ToArray()
    modelFiles = $modelFiles.ToArray()
    migrations = $migrations.ToArray()
    seedRequirements = $seedRequirements.ToArray()
    initScript = "scripts\migrate.ps1"
    checkScript = "scripts\check-db.ps1"
}

$jsonPath = Join-Path $outputFullPath "db-assembly-plan.json"
$dbPlan | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $jsonPath

Write-Host "DB assembly plan written to $jsonPath"
