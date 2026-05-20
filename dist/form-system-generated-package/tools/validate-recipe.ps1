param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$RecipePath = "assembly\form-analysis-original.recipe.json",
    [string]$ManifestPath = "kits\form-analysis.kit-manifest.json"
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

function Add-Error([System.Collections.Generic.List[string]]$Errors, [string]$Message) {
    $Errors.Add($Message)
}

$recipe = Read-JsonUtf8 (Join-Path $ProjectRoot $RecipePath)
$manifest = Read-JsonUtf8 (Join-Path $ProjectRoot $ManifestPath)
$errors = New-Object System.Collections.Generic.List[string]

$kitMap = @{}
foreach ($kit in @($manifest.kits)) {
    $kitMap[[string]$kit.id] = $kit
}

foreach ($kitId in @($recipe.enabledKits)) {
    if (-not $kitMap.ContainsKey([string]$kitId)) {
        Add-Error $errors "enabledKits contains unknown kit: $kitId"
    }
}

foreach ($kit in @($manifest.kits | Where-Object { $_.required })) {
    if (-not @($recipe.enabledKits).Contains($kit.id)) {
        Add-Error $errors "required kit is missing from recipe: $($kit.id)"
    }
}

if ($recipe.selectedSubfeatures) {
    foreach ($property in $recipe.selectedSubfeatures.PSObject.Properties) {
        $kitId = [string]$property.Name
        if (-not $kitMap.ContainsKey($kitId)) {
            Add-Error $errors "selectedSubfeatures contains unknown kit: $kitId"
            continue
        }
        if (-not @($recipe.enabledKits).Contains($kitId)) {
            Add-Error $errors "selectedSubfeatures contains kit that is not enabled: $kitId"
        }

        $subfeatureIds = @($kitMap[$kitId].subfeatures | ForEach-Object { [string]$_.id })
        foreach ($subfeatureId in @($property.Value)) {
            if (-not $subfeatureIds.Contains([string]$subfeatureId)) {
                Add-Error $errors "selectedSubfeatures.$kitId contains unknown subfeature: $subfeatureId"
            }
        }
    }
}

if ($recipe.selectedSubfeatureOptions) {
    foreach ($property in $recipe.selectedSubfeatureOptions.PSObject.Properties) {
        if ($property.Name -notmatch "^[a-z0-9-]+::[a-z0-9-]+$") {
            Add-Error $errors "selectedSubfeatureOptions key must be kit::subfeature: $($property.Name)"
        }
    }
}

if ($null -ne $recipe.featureFlags -and $recipe.featureFlags -is [System.Array]) {
    Add-Error $errors "featureFlags must be an object (key-value map), not an array"
}

foreach ($nav in @($recipe.frontendNavigation)) {
    if (-not $kitMap.ContainsKey([string]$nav.kit)) {
        Add-Error $errors "frontendNavigation contains unknown kit: $($nav.kit)"
    }
    elseif (-not @($recipe.enabledKits).Contains([string]$nav.kit)) {
        Add-Error $errors "frontendNavigation references disabled kit: $($nav.kit)"
    }
}

if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Error $_ }
    throw "Recipe validation failed: $RecipePath"
}

Write-Host "OK $RecipePath"
