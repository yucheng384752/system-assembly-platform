param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ResolvedPlanPath = "assembly\resolved-plan.json",
    [string]$ManifestPath = "kits\form-analysis.kit-manifest.json",
    [string]$RequirementsBaselinePath = "assembly\baselines\default-requirements.baseline.json",
    [string]$DbSchemaBaselinePath = "assembly\baselines\default-db-schema.baseline.json",
    [string]$DaihuiSchemaBaselinePath = "assembly\baselines\daihui-form-schema.baseline.json",
    [string]$EntitlementPlanPath = "assembly\entitlement-plan\entitlement-plan.json",
    [string]$OutputPath = "assembly\assembly-ir.json"
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

function Read-JsonIfExists([string]$Path) {
    if (-not (Test-Path $Path)) {
        return $null
    }
    return Read-JsonUtf8 $Path
}

function Get-ObjectPropertyValue([object]$Object, [string]$Name) {
    if ($null -eq $Object -or -not $Object.PSObject.Properties[$Name]) {
        return $null
    }
    return $Object.PSObject.Properties[$Name].Value
}

function Add-UniqueRuntimeNode([System.Collections.Generic.List[object]]$Nodes, [System.Collections.Generic.HashSet[string]]$Seen, [string]$Id, [string]$Kind, [string]$Owner) {
    if ([string]::IsNullOrWhiteSpace($Id) -or $Seen.Contains($Id)) {
        return
    }
    [void]$Seen.Add($Id)
    $Nodes.Add([ordered]@{
        id = $Id
        kind = $Kind
        owner = $Owner
    })
}

$resolvedPlanFullPath = Join-Path $ProjectRoot $ResolvedPlanPath
$manifestFullPath = Join-Path $ProjectRoot $ManifestPath
$requirementsBaselineFullPath = Join-Path $ProjectRoot $RequirementsBaselinePath
$dbSchemaBaselineFullPath = Join-Path $ProjectRoot $DbSchemaBaselinePath
$daihuiSchemaBaselineFullPath = Join-Path $ProjectRoot $DaihuiSchemaBaselinePath
$entitlementPlanFullPath = Join-Path $ProjectRoot $EntitlementPlanPath
$outputFullPath = Join-Path $ProjectRoot $OutputPath

$plan = Read-JsonUtf8 $resolvedPlanFullPath
$manifest = Read-JsonUtf8 $manifestFullPath
$requirementsBaseline = Read-JsonIfExists $requirementsBaselineFullPath
$dbSchemaBaseline = Read-JsonIfExists $dbSchemaBaselineFullPath
$daihuiSchemaBaseline = Read-JsonIfExists $daihuiSchemaBaselineFullPath
$entitlementPlan = Read-JsonIfExists $entitlementPlanFullPath

$kitMap = @{}
foreach ($kit in @($manifest.kits)) {
    $kitMap[[string]$kit.id] = $kit
}

$selectedKits = New-Object System.Collections.Generic.List[object]
foreach ($kitId in @($plan.resolvedKitOrder)) {
    $kit = $kitMap[[string]$kitId]
    $selectedKits.Add([ordered]@{
        id = [string]$kit.id
        displayName = [string]$kit.displayName
        category = [string]$kit.category
        required = [bool]$kit.required
        selectedSubfeatures = @((Get-ObjectPropertyValue $plan.selectedSubfeatures ([string]$kitId)))
        selectedSubfeatureOptions = Get-ObjectPropertyValue $plan.selectedSubfeatureOptions ([string]$kitId)
        dependencies = @($kit.dependencies | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
        optionalDependencies = @($kit.optionalDependencies | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    })
}

$frontendNavigation = New-Object System.Collections.Generic.List[object]
foreach ($nav in @($plan.frontendNavigation)) {
    $kit = $kitMap[[string]$nav.kit]
    if ($null -eq $kit) {
        continue
    }
    $frontendNavigation.Add([ordered]@{
        tab = [string]$nav.tab
        labelKey = [string]$nav.labelKey
        kit = [string]$nav.kit
        visibleWhen = if ($nav.PSObject.Properties["visibleWhen"]) { [string]$nav.visibleWhen } else { $null }
        pages = @($kit.frontend.pages | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
        services = @($kit.frontend.services | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    })
}

$storageDecisions = New-Object System.Collections.Generic.List[object]
if ($dbSchemaBaseline -and $dbSchemaBaseline.tables) {
    foreach ($tableProperty in $dbSchemaBaseline.tables.PSObject.Properties) {
        $table = $tableProperty.Value
        $storageDecisions.Add([ordered]@{
            subject = [string]$tableProperty.Name
            storage = "physical-table"
            kitOwner = [string]$table.kitOwner
            contractStatus = [string]$table.contractStatus
            reason = "Canonical runtime table from the default DB schema baseline."
        })
    }
}
if ($daihuiSchemaBaseline) {
    foreach ($domainTable in @($daihuiSchemaBaseline.domainTables.PSObject.Properties)) {
        $storageDecisions.Add([ordered]@{
            subject = "daihui.$($domainTable.Name)"
            storage = [string]$domainTable.Value.storage
            kitOwner = "station-data-link-kit"
            contractStatus = "schema-pack"
            reason = [string]$domainTable.Value.purpose
        })
    }
    foreach ($form in @($daihuiSchemaBaseline.forms)) {
        $storageDecisions.Add([ordered]@{
            subject = "daihui.form.$($form.formCode)"
            storage = "generic_records + JSONB data"
            kitOwner = "station-data-link-kit"
            contractStatus = "hybrid-generic"
            reason = "Daihui sample form rows keep common query fields physically extracted and preserve full source rows in JSONB."
        })
    }
}

$runtimeNodes = New-Object System.Collections.Generic.List[object]
$runtimeEdges = New-Object System.Collections.Generic.List[object]
$seenNodes = New-Object System.Collections.Generic.HashSet[string]
Add-UniqueRuntimeNode $runtimeNodes $seenNodes "runtime:tenant" "identity-scope" "tenant-auth-kit"
Add-UniqueRuntimeNode $runtimeNodes $seenNodes "runtime:api-key" "actor-credential" "tenant-auth-kit"
Add-UniqueRuntimeNode $runtimeNodes $seenNodes "runtime:database" "state-store" "platform-core-kit"
Add-UniqueRuntimeNode $runtimeNodes $seenNodes "runtime:env" "configuration" "platform-core-kit"

foreach ($registration in @($plan.backendRouterRegistrations)) {
    $nodeId = "router:$($registration.module)"
    Add-UniqueRuntimeNode $runtimeNodes $seenNodes $nodeId "backend-router" ([string]$registration.kit)
    $runtimeEdges.Add([ordered]@{
        from = $nodeId
        to = "runtime:tenant"
        kind = if ([bool]$registration.tenantScoped) { "tenant-scoped" } else { "public-or-system" }
    })
}

foreach ($model in @($plan.requiredModels)) {
    $nodeId = "model:$model"
    Add-UniqueRuntimeNode $runtimeNodes $seenNodes $nodeId "database-model" $null
    $runtimeEdges.Add([ordered]@{
        from = $nodeId
        to = "runtime:database"
        kind = "persists-to"
    })
}

foreach ($service in @($plan.selectedExternalServices)) {
    $nodeId = "external:$($service.id)"
    Add-UniqueRuntimeNode $runtimeNodes $seenNodes $nodeId "external-service" ([string]$service.kit)
    $runtimeEdges.Add([ordered]@{
        from = $nodeId
        to = "runtime:env"
        kind = "configured-by:$($service.config)"
    })
}

$env = [ordered]@{
    DATABASE_URL = "required"
    SECRET_KEY = "required"
    CORS_ORIGINS = "required"
    AUTH_MODE = $plan.featureFlags.AUTH_MODE
    MULTI_TENANT_ENABLED = $plan.featureFlags.MULTI_TENANT_ENABLED
    USE_GENERIC_SCHEMA = $plan.featureFlags.USE_GENERIC_SCHEMA
    AUDIT_EVENTS_ENABLED = $plan.featureFlags.AUDIT_EVENTS_ENABLED
}
foreach ($service in @($plan.selectedExternalServices)) {
    if (-not [string]::IsNullOrWhiteSpace([string]$service.config)) {
        $env[[string]$service.config] = if ([bool]$service.required) { "required" } else { "optional" }
    }
}

$kitInstallPlan = New-Object System.Collections.Generic.List[object]
foreach ($kitId in @($plan.resolvedKitOrder)) {
    $kitInstallManifestPath = Join-Path $ProjectRoot "kits\$kitId\manifest.json"
    if (-not (Test-Path $kitInstallManifestPath)) {
        throw "Kit install manifest not found: $kitInstallManifestPath"
    }

    $kitInstallManifest = Read-JsonUtf8 $kitInstallManifestPath
    $kitInstallPlan.Add([pscustomobject][ordered]@{
        kit = [string]$kitId
        order = [int]$kitInstallManifest.installOrder
        requires = @($kitInstallManifest.requires)
        env = @($kitInstallManifest.runtimeEnv)
        scripts = @("kits/$kitId/install.ps1")
    })
}
$kitInstallPlanSorted = @($kitInstallPlan.ToArray() | Sort-Object order)

$ir = [ordered]@{
    irVersion = "0.1.0"
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
    sourceRecipe = [ordered]@{
        id = [string]$plan.recipe
        resolvedPlanPath = $ResolvedPlanPath
        sourceManifest = [string]$plan.sourceManifest
        manifestPath = $ManifestPath
        databaseRecommendation = $manifest.defaultDatabaseRecommendation
    }
    selectedKits = $selectedKits.ToArray()
    featureFlags = $plan.featureFlags
    frontend = [ordered]@{
        sources = @($plan.frontendSources)
        navigation = $frontendNavigation.ToArray()
    }
    backend = [ordered]@{
        sources = @($plan.backendSources)
        enabledApis = @($plan.enabledApis | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
        requiredModels = @($plan.requiredModels)
        routerRegistrations = @($plan.backendRouterRegistrations)
    }
    database = [ordered]@{
        engine = [string]$plan.database.engine
        selectedByUserIntent = $plan.database.selectedByUserIntent
        reasonForNonTechnicalUser = $plan.database.reasonForNonTechnicalUser
        physicalFirstStorage = [ordered]@{
            strategy = "hybrid-physical-first"
            decisions = $storageDecisions.ToArray()
        }
        dataFlowDefinition = if ($daihuiSchemaBaseline) { (Get-ObjectPropertyValue $daihuiSchemaBaseline "dataFlowDefinition") } else { $null }
        baselines = [ordered]@{
            defaultDbSchema = $dbSchemaBaseline
            daihuiFormSchema = $daihuiSchemaBaseline
        }
    }
    dependencies = [ordered]@{
        baseline = $requirementsBaseline
        runtimeDependenciesByKit = @($manifest.kits | Where-Object { @($plan.resolvedKitOrder).Contains([string]$_.id) -and $_.runtimeDependencies } | ForEach-Object {
            [ordered]@{
                kit = [string]$_.id
                runtimeDependencies = $_.runtimeDependencies
            }
        })
    }
    env = $env
    scripts = @(
        "scripts\check-prerequisites.ps1",
        "scripts\check-db.ps1",
        "scripts\configure-env.ps1",
        "scripts\install.ps1",
        "scripts\migrate.ps1",
        "scripts\smoke-start.ps1",
        "scripts\status.ps1",
        "scripts\stop.ps1",
        "scripts\restart.ps1",
        "scripts\start.ps1"
    )
    kitInstallPlan = $kitInstallPlanSorted
    entitlements = [ordered]@{
        checks = if ($entitlementPlan) { @($entitlementPlan.checks) } else { @() }
        planMatrix = if ($entitlementPlan) { $entitlementPlan.planMatrix } else { [ordered]@{} }
    }
    runtimeStateTopology = [ordered]@{
        nodes = $runtimeNodes.ToArray()
        edges = $runtimeEdges.ToArray()
    }
}

$outputDirectory = Split-Path -Parent $outputFullPath
if (-not (Test-Path $outputDirectory)) {
    New-Item -ItemType Directory -Force $outputDirectory | Out-Null
}

$ir | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 $outputFullPath
Write-Host "Assembly IR written to $outputFullPath"
