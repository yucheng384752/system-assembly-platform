param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ResolvedPlanPath = "assembly\resolved-plan.json",
    [string]$ManifestPath = "kits\form-analysis.kit-manifest.json",
    [string]$OutputDirectory = "assembly\db-plan",
    [string]$DefaultSchemaBaselinePath = "assembly\baselines\default-db-schema.baseline.json",
    [string]$DomainSchemaPackPath = "assembly\baselines\daihui-form-schema.baseline.json"
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

function Get-JsonHash([object]$Value) {
    $json = $Value | ConvertTo-Json -Depth 50 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Get-HeaderFingerprint([string[]]$Headers) {
    $normalized = ($Headers | ForEach-Object { $_.Trim() } | Sort-Object) -join "|"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function ConvertTo-OrderedJsonObject([object]$Value) {
    return $Value | ConvertTo-Json -Depth 50 | ConvertFrom-Json
}

function Infer-DaihuiSampleSchema([object]$SchemaPack, [string]$ProjectRoot) {
    $sourceDirectory = [string]$SchemaPack.sourceDirectory
    $reportForms = New-Object System.Collections.Generic.List[object]
    $sampleFiles = New-Object System.Collections.Generic.List[object]

    foreach ($form in @($SchemaPack.forms)) {
        $samplePath = Join-Path $sourceDirectory ([string]$form.sampleFile)
        $rows = @()
        if (Test-Path $samplePath) {
            $rows = @(Import-Csv -LiteralPath $samplePath -Encoding UTF8)
        }

        $headers = @()
        if ($rows.Count -gt 0) {
            $headers = @($rows[0].PSObject.Properties.Name)
        } else {
            $headers = @($form.fields | ForEach-Object { [string]$_.sourceName })
        }

        $fieldReport = New-Object System.Collections.Generic.List[object]
        foreach ($field in @($form.fields)) {
            $sourceName = [string]$field.sourceName
            $sampleValues = @()
            foreach ($row in $rows) {
                $prop = $row.PSObject.Properties[$sourceName]
                if ($null -ne $prop -and -not [string]::IsNullOrWhiteSpace([string]$prop.Value)) {
                    $sampleValues += [string]$prop.Value
                }
            }

            $fieldReport.Add([ordered]@{
                sourceName = $sourceName
                fieldKey = [string]$field.fieldKey
                role = [string]$field.role
                declaredType = [string]$field.type
                sampleValues = @($sampleValues | Select-Object -First 3)
                nullable = $sampleValues.Count -lt $rows.Count
            })
        }

        $reportForms.Add([ordered]@{
            formCode = [string]$form.formCode
            displayName = [string]$form.displayName
            sampleFile = [string]$form.sampleFile
            samplePath = $samplePath
            rowCount = $rows.Count
            headers = $headers
            headerFingerprint = Get-HeaderFingerprint $headers
            fields = $fieldReport.ToArray()
        })

        $sampleFiles.Add([ordered]@{
            formCode = [string]$form.formCode
            file = [string]$form.sampleFile
            path = $samplePath
            rowCount = $rows.Count
            headerFingerprint = Get-HeaderFingerprint $headers
        })
    }

    return [ordered]@{
        generatedAt = (Get-Date).ToString("s")
        sourceDirectory = $sourceDirectory
        strategy = [string]$SchemaPack.strategy
        sampleScope = [string]$SchemaPack.sampleScope
        forms = $reportForms.ToArray()
        sampleFiles = $sampleFiles.ToArray()
    }
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

$defaultSchemaBaseline = $null
$defaultSchemaBaselineFullPath = Join-Path $ProjectRoot $DefaultSchemaBaselinePath
if (Test-Path $defaultSchemaBaselineFullPath) {
    $defaultSchemaBaseline = Read-JsonUtf8 $defaultSchemaBaselineFullPath
}

$domainSchemaPack = $null
$domainSchemaPackFullPath = Join-Path $ProjectRoot $DomainSchemaPackPath
$clientFormSchemas = @($plan.formSchemas | Where-Object { $null -ne $_ })
if ($clientFormSchemas.Count -eq 0 -and (Test-Path $domainSchemaPackFullPath)) {
    $domainSchemaPack = Read-JsonUtf8 $domainSchemaPackFullPath
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

$tables = [ordered]@{}
if ($null -ne $defaultSchemaBaseline -and $defaultSchemaBaseline.tables) {
    foreach ($property in $defaultSchemaBaseline.tables.PSObject.Properties) {
        $tables[$property.Name] = $property.Value
    }
}

$domainContracts = @()
$schemaVersions = @()
$seedData = [ordered]@{
    formDefinitions = @()
    schemaVersions = @()
}
$sourceSamples = @()
$relationships = @()
$indexes = @()

if ($null -ne $domainSchemaPack) {
    $domainContracts = @($domainSchemaPack)
    $indexes = @($domainSchemaPack.indexes)
    $relationships = @($domainSchemaPack.relationships)
    $sourceSamples = @($domainSchemaPack.forms | ForEach-Object {
        [ordered]@{
            formCode = [string]$_.formCode
            sampleFile = [string]$_.sampleFile
            sourceDirectory = [string]$domainSchemaPack.sourceDirectory
        }
    })

    foreach ($form in @($domainSchemaPack.forms)) {
        $schemaJson = [ordered]@{
            formCode = [string]$form.formCode
            displayName = [string]$form.displayName
            strategy = [string]$domainSchemaPack.strategy
            sampleScope = [string]$domainSchemaPack.sampleScope
            fields = @($form.fields)
            mappings = [ordered]@{
                dateColumn = $form.dateColumn
                lotColumn = $form.lotColumn
                materialColumn = $form.materialColumn
                productColumn = $form.productColumn
                quantityColumn = $form.quantityColumn
                weightColumn = $form.weightColumn
                qualityColumn = $form.qualityColumn
            }
        }
        $headers = @($form.fields | ForEach-Object { [string]$_.sourceName })
        $schemaHash = Get-JsonHash $schemaJson
        $headerFingerprint = Get-HeaderFingerprint $headers

        $schemaVersion = [ordered]@{
            formCode = [string]$form.formCode
            displayName = [string]$form.displayName
            version = 1
            schemaHash = $schemaHash
            headerFingerprint = $headerFingerprint
            schemaJson = $schemaJson
        }
        $schemaVersions += $schemaVersion
        $seedData.formDefinitions += [ordered]@{
            tableCode = [string]$form.formCode
            displayName = [string]$form.displayName
            source = "domainSchemaPack"
        }
        $seedData.schemaVersions += $schemaVersion
    }

    $inferenceReport = Infer-DaihuiSampleSchema $domainSchemaPack $ProjectRoot
    $inferencePath = Join-Path $outputFullPath "daihui-schema-inference.json"
    $inferenceReport | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 $inferencePath
}

foreach ($form in $clientFormSchemas) {
    $formCode = [string]$form.code
    if ([string]::IsNullOrWhiteSpace($formCode)) { continue }
    $schemaJson = [ordered]@{
        formCode = $formCode
        displayName = [string]$form.name
        strategy = "client-schema"
        fields = @($form.fields)
    }
    $headers = @($form.fields | ForEach-Object { [string]$_.name })
    $schemaVersion = [ordered]@{
        formCode = $formCode
        displayName = [string]$form.name
        version = 1
        schemaHash = Get-JsonHash $schemaJson
        headerFingerprint = Get-HeaderFingerprint $headers
        schemaJson = $schemaJson
    }
    $schemaVersions += $schemaVersion
    $seedData.formDefinitions += [ordered]@{
        tableCode = $formCode
        displayName = [string]$form.name
        source = "clientFormSchema"
    }
    $seedData.schemaVersions += $schemaVersion
}

$dbPlan = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    sourceRecipe = $plan.recipe
    clientName = $plan.clientName
    engine = $plan.database.engine
    connectionOwner = "platform-core-kit"
    envVars = $envVars
    models = $models.ToArray()
    modelFiles = $modelFiles.ToArray()
    migrations = $migrations.ToArray()
    tables = $tables
    relationships = $relationships
    indexes = $indexes
    schemaVersions = $schemaVersions
    seedData = $seedData
    sourceSamples = $sourceSamples
    schemaContracts = [ordered]@{
        defaultBaseline = if ($null -ne $defaultSchemaBaseline) { [ordered]@{
            path = $DefaultSchemaBaselinePath
            schemaVersion = $defaultSchemaBaseline.schemaVersion
        } } else { $null }
        domainPacks = @($domainContracts | ForEach-Object {
            [ordered]@{
                path = $DomainSchemaPackPath
                packId = [string]$_.packId
                strategy = [string]$_.strategy
                sampleScope = [string]$_.sampleScope
            }
        })
    }
    seedRequirements = $seedRequirements.ToArray()
    initScript = "scripts\migrate.ps1"
    checkScript = "scripts\check-db.ps1"
}

$jsonPath = Join-Path $outputFullPath "db-assembly-plan.json"
$dbPlan | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $jsonPath

Write-Host "DB assembly plan written to $jsonPath"
