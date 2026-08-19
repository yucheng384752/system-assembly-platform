param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$RecipePath = "assembly\form-analysis-original.recipe.json",
    [string]$ManifestPath = "kits\form-analysis.kit-manifest.json",
    [string]$OutputPath = "assembly\resolved-plan.json"
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

$manifestFullPath = Join-Path $ProjectRoot $ManifestPath
$recipeFullPath = Join-Path $ProjectRoot $RecipePath
$outputFullPath = Join-Path $ProjectRoot $OutputPath

$manifest = Read-JsonUtf8 $manifestFullPath
$recipe = Read-JsonUtf8 $recipeFullPath

$kitMap = @{}
foreach ($kit in $manifest.kits) {
    $kitMap[$kit.id] = $kit
}

$resolved = New-Object System.Collections.Generic.List[string]
$missing = New-Object System.Collections.Generic.List[object]
$visiting = New-Object System.Collections.Generic.HashSet[string]

function Add-Kit([string]$KitId) {
    if ($resolved.Contains($KitId)) {
        return
    }
    if ($script:visiting.Contains($KitId)) {
        $script:missing.Add([ordered]@{
            kit    = $KitId
            reason = "Circular dependency detected"
        })
        return
    }
    if (-not $kitMap.ContainsKey($KitId)) {
        $script:missing.Add([ordered]@{
            kit    = $KitId
            reason = "Kit id not found in manifest"
        })
        return
    }

    $null = $script:visiting.Add($KitId)
    $kit = $kitMap[$KitId]
    foreach ($dep in @($kit.dependencies)) {
        Add-Kit $dep
    }
    $null = $script:visiting.Remove($KitId)
    if (-not $resolved.Contains($KitId)) {
        $resolved.Add($KitId)
    }
}

function Get-RecipeSelectedSubfeatureIds([object]$Recipe, [object]$Kit) {
    if (-not $Kit.subfeatures) {
        return @()
    }

    if (-not $Recipe.selectedSubfeatures) {
        return @($Kit.subfeatures | Where-Object { $false -ne $_.defaultSelected } | ForEach-Object { [string]$_.id })
    }

    $property = $Recipe.selectedSubfeatures.PSObject.Properties[[string]$Kit.id]
    if ($null -eq $property) {
        return @($Kit.subfeatures | Where-Object { $false -ne $_.defaultSelected } | ForEach-Object { [string]$_.id })
    }

    return @($property.Value | ForEach-Object { [string]$_ })
}

function Get-SubfeatureMap([object]$Kit) {
    $map = @{}
    foreach ($subfeature in @($Kit.subfeatures)) {
        $map[[string]$subfeature.id] = $subfeature
    }
    return $map
}

function Test-ServiceConfigBound([object]$FeatureFlags, [string]$ConfigName) {
    if ([string]::IsNullOrWhiteSpace($ConfigName)) {
        return $false
    }

    if (-not $FeatureFlags.Contains($ConfigName)) {
        return $false
    }

    $value = [string]$FeatureFlags[$ConfigName]
    return -not [string]::IsNullOrWhiteSpace($value) -and $value -ne "optional"
}

foreach ($kitId in @($recipe.enabledKits)) {
    Add-Kit $kitId
}

$enabledApis = New-Object System.Collections.Generic.List[string]
$models = New-Object System.Collections.Generic.List[string]
$frontendSources = New-Object System.Collections.Generic.List[string]
$backendSources = New-Object System.Collections.Generic.List[string]
$templateSources = New-Object System.Collections.Generic.List[string]
$backendRouterRegistrations = New-Object System.Collections.Generic.List[object]
$externalServices = New-Object System.Collections.Generic.List[object]
$featureFlags = [ordered]@{}

foreach ($kitId in $resolved) {
    $kit = $kitMap[$kitId]
    foreach ($api in @($kit.api)) {
        $apiName = [string]$api
        if (-not [string]::IsNullOrWhiteSpace($apiName) -and -not $enabledApis.Contains($apiName)) {
            $enabledApis.Add($apiName)
        }
    }
    if ($kit.database -and $kit.database.models) {
        foreach ($model in @($kit.database.models)) {
            if (-not $models.Contains($model)) {
                $models.Add($model)
            }
        }
    }
    foreach ($source in @($kit.frontend.pages) + @($kit.frontend.components) + @($kit.frontend.services) + @($kit.frontend.hooks) + @($kit.frontend.shellFiles)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$source) -and -not $frontendSources.Contains($source)) {
            $frontendSources.Add($source)
        }
    }
    foreach ($source in @($kit.backend.routers) + @($kit.backend.core) + @($kit.backend.services) + @($kit.backend.models)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$source) -and -not $backendSources.Contains($source)) {
            $backendSources.Add($source)
        }
    }
    foreach ($source in @($kit.templates.backend) + @($kit.templates.frontend)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$source) -and -not $templateSources.Contains($source)) {
            $templateSources.Add($source)
        }
    }
    foreach ($registration in @($kit.backend.routerRegistrations)) {
        if ($null -ne $registration) {
            $backendRouterRegistrations.Add([ordered]@{
                kit = $kitId
                module = $registration.module
                symbol = $registration.symbol
                prefix = $registration.prefix
                tags = @($registration.tags)
                tenantScoped = [bool]$registration.tenantScoped
                featureFlag = $registration.featureFlag
            })
        }
    }
    foreach ($service in @($kit.externalServices)) {
        if ($null -ne $service) {
            $externalServices.Add($service)
        }
    }
    foreach ($flag in @($kit.featureFlags)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$flag)) {
            $featureFlags[[string]$flag] = $true
        }
    }
}

if ($recipe.featureFlags) {
    $recipe.featureFlags.PSObject.Properties | ForEach-Object {
        $featureFlags[$_.Name] = $_.Value
    }
}

$selectedSubfeatures = [ordered]@{}
$selectedExternalServices = New-Object System.Collections.Generic.List[object]

foreach ($kitId in $resolved) {
    $kit = $kitMap[$kitId]
    $subfeatureMap = Get-SubfeatureMap $kit
    $selectedIds = Get-RecipeSelectedSubfeatureIds $recipe $kit
    $validSelectedIds = New-Object System.Collections.Generic.List[string]

    foreach ($subfeatureId in $selectedIds) {
        if ([string]::IsNullOrWhiteSpace($subfeatureId)) {
            continue
        }

        if (-not $subfeatureMap.ContainsKey($subfeatureId)) {
            $missing.Add([ordered]@{
                kit = $kitId
                subfeature = $subfeatureId
                reason = "Subfeature id not found in manifest"
            })
            continue
        }

        $subfeature = $subfeatureMap[$subfeatureId]
        $validSelectedIds.Add($subfeatureId)

        foreach ($dependency in @($subfeature.dependencies)) {
            if ([string]::IsNullOrWhiteSpace([string]$dependency)) {
                continue
            }

            $dependencyKitId = $kitId
            $dependencySubfeatureId = [string]$dependency
            if ($dependencySubfeatureId.Contains(":")) {
                $parts = $dependencySubfeatureId.Split(":", 2)
                $dependencyKitId = $parts[0]
                $dependencySubfeatureId = $parts[1]
            }

            if (-not $selectedSubfeatures.Contains($dependencyKitId)) {
                $dependencyKit = $kitMap[$dependencyKitId]
                if ($null -ne $dependencyKit) {
                    $selectedSubfeatures[$dependencyKitId] = @(Get-RecipeSelectedSubfeatureIds $recipe $dependencyKit)
                }
            }

            if (-not $selectedSubfeatures.Contains($dependencyKitId) -or -not @($selectedSubfeatures[$dependencyKitId]).Contains($dependencySubfeatureId)) {
                $missing.Add([ordered]@{
                    kit = $kitId
                    subfeature = $subfeatureId
                    reason = "Required subfeature dependency is not selected: $dependency"
                })
            }
        }

        foreach ($service in @($subfeature.externalServices)) {
            if ($null -eq $service) {
                continue
            }

            $selectedExternalServices.Add([ordered]@{
                kit = $kitId
                subfeature = $subfeatureId
                id = $service.id
                config = $service.config
                required = [bool]$service.required
            })

            if ($service.required -and -not (Test-ServiceConfigBound $featureFlags ([string]$service.config))) {
                $missing.Add([ordered]@{
                    kit = $kitId
                    subfeature = $subfeatureId
                    service = $service.id
                    config = $service.config
                    reason = "Required external service config is not bound"
                })
            }
        }
    }

    $selectedSubfeatures[$kitId] = $validSelectedIds.ToArray()
}

$plan = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    recipe = $recipe.name
    clientName = $recipe.clientName
    sourceManifest = $manifest.name
    database = $recipe.database
    resolvedKitOrder = $resolved.ToArray()
    selectedSubfeatures = $selectedSubfeatures
    selectedSubfeatureOptions = $recipe.selectedSubfeatureOptions
    missing = $missing.ToArray()
    enabledApis = $enabledApis.ToArray()
    requiredModels = $models.ToArray()
    frontendSources = $frontendSources.ToArray()
    backendSources = $backendSources.ToArray()
    templateSources = $templateSources.ToArray()
    backendRouterRegistrations = $backendRouterRegistrations.ToArray()
    externalServices = $externalServices.ToArray()
    selectedExternalServices = $selectedExternalServices.ToArray()
    featureFlags = $featureFlags
    frontendNavigation = $recipe.frontendNavigation
    previewScenarios = $recipe.previewScenarios
    dataflows = @($recipe.dataflows | Where-Object { $null -ne $_ })
    formSchemas = @($recipe.formSchemas | Where-Object { $null -ne $_ })
}

$outDir = Split-Path -Parent $outputFullPath
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Force $outDir | Out-Null
}

$plan | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $outputFullPath
Write-Host "Resolved plan written to $outputFullPath"
