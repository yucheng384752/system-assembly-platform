param(
    [Parameter(Mandatory = $true)][string]$PackagePath,
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$OutputPath,
    [switch]$PassThru
)

$ErrorActionPreference = "Stop"
$validatorVersion = "1.0.0"

function Read-Json([string]$Path) {
    Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
}

function Has-Property($Object, [string]$Name) {
    $null -ne $Object -and $null -ne $Object.PSObject.Properties[$Name]
}

function Values($Value) {
    if ($null -eq $Value) { return @() }
    @($Value | Where-Object { $null -ne $_ })
}

function Add-Finding($Target, [string]$Code, [string]$Message, $Evidence = $null, [string]$Severity = "fail") {
    $Target.findings.Add([ordered]@{ code = $Code; severity = $Severity; message = $Message; evidence = $Evidence })
    if ($Severity -eq "fail") { $Target.status = "fail" }
    elseif ($Severity -eq "warning" -and $Target.status -eq "pass") { $Target.status = "warning" }
}

function New-Gate([string]$Id) {
    [ordered]@{ id = $Id; status = "pass"; findings = [System.Collections.Generic.List[object]]::new(); evidence = [System.Collections.Generic.List[object]]::new(); remediation = @() }
}

function Resolve-SchemaReference($Root, [string]$Reference) {
    if (-not $Reference.StartsWith("#/")) { throw "Unsupported schema reference: $Reference" }
    $value = $Root
    foreach ($part in $Reference.Substring(2).Split('/')) {
        $name = $part.Replace('~1', '/').Replace('~0', '~')
        $value = $value.PSObject.Properties[$name].Value
    }
    $value
}

function Test-SchemaNode($Value, $Schema, $Root, [string]$Path, [System.Collections.Generic.List[string]]$Errors) {
    if ((Has-Property $Schema '$ref')) {
        Test-SchemaNode $Value (Resolve-SchemaReference $Root ([string]$Schema.'$ref')) $Root $Path $Errors
        return
    }

    $types = Values $Schema.type
    if ($types.Count -gt 0) {
        $actual = if ($null -eq $Value) { "null" }
            elseif ($Value -is [string]) { "string" }
            elseif ($Value -is [bool]) { "boolean" }
            elseif ($Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64]) { "integer" }
            elseif ($Value -is [decimal] -or $Value -is [double] -or $Value -is [single]) { "number" }
            elseif ($Value -is [System.Array]) { "array" }
            elseif ($Value -is [System.Collections.IDictionary] -or $Value -is [pscustomobject]) { "object" }
            else { "unknown" }
        if ($actual -eq "integer" -and $types -contains "number") { $actual = "number" }
        if ($types -notcontains $actual) {
            $Errors.Add("$Path must be $($types -join '|'), got $actual")
            return
        }
    }

    if ($null -eq $Value) { return }
    if ($Value -is [string]) {
        if ((Has-Property $Schema 'minLength') -and $Value.Length -lt [int]$Schema.minLength) { $Errors.Add("$Path is shorter than minLength") }
        if ((Has-Property $Schema 'pattern') -and $Value -notmatch [string]$Schema.pattern) { $Errors.Add("$Path does not match pattern $($Schema.pattern)") }
    }
    if ((Has-Property $Schema 'enum') -and (Values $Schema.enum) -notcontains $Value) { $Errors.Add("$Path is not an allowed value") }

    if ($Value -is [System.Array]) {
        if ((Has-Property $Schema 'minItems') -and $Value.Count -lt [int]$Schema.minItems) { $Errors.Add("$Path has too few items") }
        if ((Has-Property $Schema 'uniqueItems') -and $Schema.uniqueItems) {
            $serialized = @($Value | ForEach-Object { $_ | ConvertTo-Json -Depth 50 -Compress })
            if (@($serialized | Select-Object -Unique).Count -ne $serialized.Count) { $Errors.Add("$Path contains duplicate items") }
        }
        if ((Has-Property $Schema 'items')) {
            for ($index = 0; $index -lt $Value.Count; $index++) { Test-SchemaNode $Value[$index] $Schema.items $Root "$Path[$index]" $Errors }
        }
        return
    }

    if ($Value -is [System.Collections.IDictionary] -or $Value -is [pscustomobject]) {
        $names = @($Value.PSObject.Properties.Name)
        foreach ($required in Values $Schema.required) {
            if ($names -notcontains [string]$required) { $Errors.Add("$Path is missing required property '$required'") }
        }
        if ((Has-Property $Schema 'properties')) {
            foreach ($property in $Schema.properties.PSObject.Properties) {
                if ($names -contains $property.Name) { Test-SchemaNode $Value.PSObject.Properties[$property.Name].Value $property.Value $Root "$Path.$($property.Name)" $Errors }
            }
        }
        if ((Has-Property $Schema 'additionalProperties')) {
            $known = if ((Has-Property $Schema 'properties')) { @($Schema.properties.PSObject.Properties.Name) } else { @() }
            foreach ($name in $names | Where-Object { $known -notcontains $_ }) {
                if ($false -eq $Schema.additionalProperties) { $Errors.Add("$Path has unsupported property '$name'") }
                elseif ($Schema.additionalProperties -is [pscustomobject]) { Test-SchemaNode $Value.PSObject.Properties[$name].Value $Schema.additionalProperties $Root "$Path.$name" $Errors }
            }
        }
    }
}

function Get-CapabilityName($Capability) {
    if ($Capability -is [string]) { return [string]$Capability }
    if ((Has-Property $Capability 'capability')) { return [string]$Capability.capability }
    ""
}

function Has-Documentation($Capability, [string]$Name) {
    if (-not (Has-Property $Capability $Name)) { return $false }
    $value = $Capability.PSObject.Properties[$Name].Value
    if ($null -eq $value) { return $false }
    if ($value -is [string]) { return -not [string]::IsNullOrWhiteSpace($value) }
    if ($value -is [System.Array]) { return $value.Count -gt 0 }
    if ($value -is [pscustomobject]) { return $value.PSObject.Properties.Count -gt 0 }
    $false
}

function Get-ModelName($Model) {
    if ($Model -is [string]) { return [string]$Model }
    if ((Has-Property $Model 'name')) { return [string]$Model.name }
    ""
}

function Get-TableNames($Database) {
    if ($null -eq $Database -or -not (Has-Property $Database 'tables')) { return @() }
    if ($Database.tables -is [pscustomobject]) { return @($Database.tables.PSObject.Properties.Name) }
    @(Values $Database.tables | ForEach-Object { if ($_ -is [string]) { $_ } elseif (Has-Property $_ 'name') { $_.name } } | Where-Object { $_ })
}

function Get-SourcePaths($Definition) {
    $paths = [System.Collections.Generic.List[string]]::new()
    function Add-SectionSources($Section) {
        if ($null -eq $Section) { return }
        foreach ($name in @('pages','components','services','hooks','shellFiles','routers','core','models','backend','frontend')) {
            if (Has-Property $Section $name) {
                foreach ($path in Values $Section.PSObject.Properties[$name].Value) { if ($path -is [string] -and -not [string]::IsNullOrWhiteSpace($path)) { $paths.Add($path) } }
            }
        }
    }
    Add-SectionSources $Definition.frontend
    Add-SectionSources $Definition.backend
    Add-SectionSources $Definition.templates
    foreach ($subfeature in Values $Definition.subfeatures) {
        if (Has-Property $subfeature 'contributions') {
            Add-SectionSources $subfeature.contributions.frontend
            Add-SectionSources $subfeature.contributions.backend
            Add-SectionSources $subfeature.contributions.templates
        }
    }
    @($paths | Select-Object -Unique)
}

function Get-ConfigKeys($Definition, $InstallManifest) {
    $keys = [System.Collections.Generic.List[string]]::new()
    if ((Has-Property $Definition 'config')) { foreach ($name in $Definition.config.PSObject.Properties.Name) { $keys.Add($name) } }
    foreach ($service in Values $Definition.externalServices) { if ((Has-Property $service 'config')) { $keys.Add([string]$service.config) } }
    foreach ($subfeature in Values $Definition.subfeatures) {
        foreach ($service in Values $subfeature.externalServices) { if ((Has-Property $service 'config')) { $keys.Add([string]$service.config) } }
        if ((Has-Property $subfeature 'contributions') -and (Has-Property $subfeature.contributions 'config')) {
            foreach ($name in $subfeature.contributions.config.PSObject.Properties.Name) { $keys.Add($name) }
        }
    }
    foreach ($entry in Values $InstallManifest.runtimeEnv) {
        $name = if ($entry -is [string]) { $entry } elseif ((Has-Property $entry 'name')) { $entry.name } else { $null }
        if ($name) { $keys.Add([string]$name) }
    }
    @($keys | Where-Object { $_ } | Select-Object -Unique)
}

function Get-RouteKeys($Definition, $Contract) {
    $routes = [System.Collections.Generic.List[string]]::new()
    $apis = @(Values $Definition.api)
    foreach ($subfeature in Values $Definition.subfeatures) {
        if ((Has-Property $subfeature 'contributions') -and (Has-Property $subfeature.contributions 'api')) { $apis += Values $subfeature.contributions.api }
    }
    foreach ($api in $apis) {
        if ([string]$api -match '^\s*([A-Za-z]+)\s+(.+?)\s*$') { $routes.Add("$($matches[1].ToUpperInvariant()) $($matches[2].TrimEnd('/'))") }
    }
    foreach ($api in Values $Contract.provides.api) {
        if ($api -isnot [string] -and (Has-Property $api 'method') -and (Has-Property $api 'path')) { $routes.Add("$(([string]$api.method).ToUpperInvariant()) $(([string]$api.path).TrimEnd('/'))") }
    }
    foreach ($route in Values $Definition.backend.routerRegistrations) {
        if ((Has-Property $route 'method') -and (Has-Property $route 'prefix')) { $routes.Add("$(([string]$route.method).ToUpperInvariant()) $(([string]$route.prefix).TrimEnd('/'))") }
    }
    @($routes | Select-Object -Unique)
}

function Has-CompleteAdapter($Definition) {
    if (-not (Has-Property $Definition 'compatibility') -or -not (Has-Property $Definition.compatibility 'adapter')) { return $false }
    $adapter = $Definition.compatibility.adapter
    (Has-Property $adapter 'name') -and (Has-Property $adapter 'migration') -and (Has-Property $adapter 'rollback')
}

function Has-Replacement($Definition, $Contract, [string]$Capability) {
    if ((Has-Property $Definition 'compatibility') -and (Has-Property $Definition.compatibility 'replacesDbCapabilities') -and (Values $Definition.compatibility.replacesDbCapabilities) -contains $Capability) { return $true }
    if ((Has-Property $Contract 'replaces') -and (Has-Property $Contract.replaces 'db') -and (Values $Contract.replaces.db) -contains $Capability) { return $true }
    $false
}

$preflight = [ordered]@{ status = "pass"; findings = [System.Collections.Generic.List[object]]::new(); inventory = [System.Collections.Generic.List[object]]::new() }
$gates = @(
    (New-Gate "data-model"), (New-Gate "configuration"), (New-Gate "assembly"),
    (New-Gate "runtime"), (New-Gate "compatibility"), (New-Gate "verification")
)
$dataGate, $configGate, $assemblyGate, $runtimeGate, $compatibilityGate, $verificationGate = $gates
$definition = $installManifest = $contract = $null
$packageHash = $null
$root = $null

try { $root = (Resolve-Path -LiteralPath $PackagePath).Path } catch { Add-Finding $preflight "package.missing" "Package directory does not exist." }
if ($root -and -not (Get-Item -LiteralPath $root).PSIsContainer) { Add-Finding $preflight "package.not-directory" "Phase 1 accepts only an unpacked local directory." }

if ($preflight.status -eq "pass") {
    $queue = [System.Collections.Generic.Queue[string]]::new()
    $queue.Enqueue($root)
    $fileCount = 0; [int64]$totalBytes = 0
    while ($queue.Count -gt 0) {
        $directory = $queue.Dequeue()
        $directoryItem = Get-Item -Force -LiteralPath $directory
        if (($directoryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            Add-Finding $preflight "path.reparse-point" "Symlinks, NTFS junctions, mount points, and other reparse points are not allowed." ($directory.Substring($root.Length).TrimStart('\','/'))
            continue
        }
        foreach ($item in Get-ChildItem -Force -LiteralPath $directory) {
            $relative = $item.FullName.Substring($root.Length).TrimStart('\','/').Replace('\','/')
            $linkTypeProperty = $item.PSObject.Properties['LinkType']
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or ($null -ne $linkTypeProperty -and -not [string]::IsNullOrWhiteSpace([string]$linkTypeProperty.Value))) {
                Add-Finding $preflight "path.reparse-point" "Symlinks, NTFS junctions, mount points, and other reparse points are not allowed." "./$relative"
                continue
            }
            if ($item.PSIsContainer) { $queue.Enqueue($item.FullName); continue }
            $fileCount++; $totalBytes += $item.Length
            if ($item.Length -gt 10MB) { Add-Finding $preflight "package.file-too-large" "A package file exceeds the 10 MiB limit." "./$relative" }
            if ($item.Name -match '^(\.env(?:\..*)?|credentials?(?:\..*)?|id_rsa|id_ed25519)$' -or $item.Extension -match '^\.(pem|p12|pfx|key|sqlite|db|exe|dll|so|dylib)$') {
                Add-Finding $preflight "package.sensitive-or-binary" "Sensitive files, credential databases, private keys, and binaries are not admitted." "./$relative"
            }
            $preflight.inventory.Add([ordered]@{ path = "./$relative"; size = $item.Length; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash.ToLowerInvariant() })
        }
    }
    if ($fileCount -gt 1000) { Add-Finding $preflight "package.too-many-files" "Package exceeds the 1000 file limit." $fileCount }
    if ($totalBytes -gt 50MB) { Add-Finding $preflight "package.too-large" "Package exceeds the 50 MiB total limit." $totalBytes }
    $digestText = (($preflight.inventory | Sort-Object path | ForEach-Object { "$($_.path):$($_.sha256)" }) -join "`n")
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $packageHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($digestText)))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }

    foreach ($required in @('kit.definition.json','manifest.json','kit.contract.json')) {
        $path = Join-Path $root $required
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { Add-Finding $preflight "metadata.missing" "Required metadata file is missing: $required" }
    }
}

if ($preflight.status -eq "pass") {
    try {
        $definition = Read-Json (Join-Path $root 'kit.definition.json')
        $installManifest = Read-Json (Join-Path $root 'manifest.json')
        $contract = Read-Json (Join-Path $root 'kit.contract.json')
    } catch { Add-Finding $preflight "metadata.invalid-json" "Package metadata must be valid JSON." $_.Exception.Message }
}

$centralManifestPath = Join-Path $ProjectRoot 'kits\form-analysis.kit-manifest.json'
$schemaPath = Join-Path $ProjectRoot 'schemas\kit.schema.json'
$centralManifest = Read-Json $centralManifestPath

if ($preflight.status -eq "pass") {
    $schema = Read-Json $schemaPath
    $wrapper = [pscustomobject][ordered]@{ manifestVersion = [string]$centralManifest.manifestVersion; name = 'external-staging'; kits = @($definition) }
    $schemaErrors = [System.Collections.Generic.List[string]]::new()
    Test-SchemaNode $wrapper $schema $schema '$' $schemaErrors
    foreach ($error in $schemaErrors) { Add-Finding $configGate "definition.schema" $error }
    $configGate.evidence.Add([ordered]@{ check = 'wrapper-schema'; schema = 'schemas/kit.schema.json'; wrapper = '{manifestVersion,name,kits:[definition]}'; errors = @($schemaErrors) })

    foreach ($source in Get-SourcePaths $definition) {
        if ([IO.Path]::IsPathRooted($source) -or @($source.Replace('\','/').Split('/')) -contains '..') {
            Add-Finding $preflight "source.path-escape" "Declared source paths must be relative and may not contain '..'." $source
            continue
        }
        $relativeSource = $source.Replace('/', [IO.Path]::DirectorySeparatorChar)
        $candidate = if ($relativeSource -match '^src[\\/]') { Join-Path $root $relativeSource } else { Join-Path (Join-Path $root 'src') $relativeSource }
        if (-not (Test-Path -LiteralPath $candidate)) { Add-Finding $assemblyGate "source.missing" "Declared source does not exist: $source" $source }
    }

    $centralKitIds = @($centralManifest.kits | ForEach-Object { [string]$_.id })
    if ($centralKitIds -contains [string]$definition.id) { Add-Finding $configGate "kit.id-collision" "Kit id already exists in the central manifest: $($definition.id)" }

    $centralRoutes = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $centralDbCapabilities = @{}
    foreach ($kit in Values $centralManifest.kits) { foreach ($route in Get-RouteKeys $kit $null) { [void]$centralRoutes.Add($route) } }
    foreach ($contractFile in Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'kits') -Filter 'kit.contract.json' -File -Recurse) {
        $existing = Read-Json $contractFile.FullName
        foreach ($route in Get-RouteKeys $null $existing) { [void]$centralRoutes.Add($route) }
        foreach ($db in Values $existing.provides.db) {
            $capability = Get-CapabilityName $db
            if ($capability) { if (-not $centralDbCapabilities.ContainsKey($capability)) { $centralDbCapabilities[$capability] = @() }; $centralDbCapabilities[$capability] += [string]$existing.kit }
        }
    }
    foreach ($route in Get-RouteKeys $definition $contract) { if ($centralRoutes.Contains($route)) { Add-Finding $assemblyGate "route.collision" "Route collides with the central system: $route" $route } }

    $centralModels = @($centralManifest.kits | ForEach-Object { Values $_.database.models | ForEach-Object { Get-ModelName $_ } } | Where-Object { $_ })
    $externalModels = @(Values $definition.database.models | ForEach-Object { Get-ModelName $_ } | Where-Object { $_ })
    foreach ($model in $externalModels) { if ($centralModels -contains $model) { Add-Finding $dataGate "model.collision" "Model collides with the central system: $model" $model } }

    $baseline = Read-Json (Join-Path $ProjectRoot 'assembly\baselines\default-db-schema.baseline.json')
    $centralTables = @($baseline.tables.PSObject.Properties.Name)
    $externalTables = @(Get-TableNames $definition.database)
    foreach ($table in $externalTables) { if ($centralTables -contains $table) { Add-Finding $dataGate "table.collision" "Table collides with the central system: $table" $table } }

    $centralConfig = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($kit in Values $centralManifest.kits) { foreach ($key in Get-ConfigKeys $kit $null) { [void]$centralConfig.Add($key) } }
    foreach ($manifestFile in Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'kits') -Filter 'manifest.json' -File -Recurse) { foreach ($key in Get-ConfigKeys $null (Read-Json $manifestFile.FullName)) { [void]$centralConfig.Add($key) } }
    foreach ($key in Get-ConfigKeys $definition $installManifest) { if ($centralConfig.Contains($key)) { Add-Finding $configGate "config.collision" "Config key collides with the central system: $key" $key } }

    foreach ($db in Values $contract.provides.db) {
        $capability = Get-CapabilityName $db
        if ($capability -and $centralDbCapabilities.ContainsKey($capability) -and -not (Has-Replacement $definition $contract $capability)) {
            Add-Finding $assemblyGate "db-capability.duplicate-provider" "DB capability '$capability' is already provided by $($centralDbCapabilities[$capability] -join ', ')." $capability
        }
    }

    $sharedModels = @()
    if ((Has-Property $definition.database 'tenantSharedModels')) { $sharedModels += Values $definition.database.tenantSharedModels }
    if ((Has-Property $definition.database 'globalModels')) { $sharedModels += Values $definition.database.globalModels }
    foreach ($model in $externalModels) {
        $tenantPath = $false
        foreach ($route in Values $definition.backend.routerRegistrations) {
            $targets = @(); if ((Has-Property $route 'model')) { $targets += [string]$route.model }; if ((Has-Property $route 'models')) { $targets += Values $route.models }
            if ($route.tenantScoped -eq $true -and $targets -contains $model) { $tenantPath = $true }
        }
        foreach ($db in Values $contract.provides.db) {
            if ($db -is [string]) { continue }
            $targets = @(); if ((Has-Property $db 'model')) { $targets += [string]$db.model }; if ((Has-Property $db 'models')) { $targets += Values $db.models }
            if ($db.tenantScoped -eq $true -and $targets -contains $model) { $tenantPath = $true }
        }
        if (-not $tenantPath -and $sharedModels -notcontains $model) { Add-Finding $dataGate "tenant.boundary-missing" "Model '$model' has no tenantScoped router/provides.db path and is not declared tenant-shared/global." $model }
    }

    foreach ($scriptProperty in Values $installManifest.scripts.PSObject.Properties) {
        $scriptName = [string]$scriptProperty.Value
        if ([IO.Path]::IsPathRooted($scriptName) -or @($scriptName.Replace('\','/').Split('/')) -contains '..') { Add-Finding $runtimeGate "script.path-escape" "Install script path escapes the package: $scriptName"; continue }
        $scriptPath = Join-Path $root $scriptName
        if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { Add-Finding $runtimeGate "script.missing" "Declared install script is missing: $scriptName"; continue }
        $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $scriptPath
        if ($text -match '(?i)Invoke-WebRequest|Invoke-RestMethod|\bcurl(?:\.exe)?\b|\bwget\b|https?://') { Add-Finding $runtimeGate "script.network" "Install scripts may not download from the network during admission." $scriptName }
        $declaredEnv = @(Get-ConfigKeys $null $installManifest)
        foreach ($match in [regex]::Matches($text, '(?i)(?:\$env:|\$\{?)([A-Z][A-Z0-9_]{2,})')) {
            if ($declaredEnv -notcontains $match.Groups[1].Value) { Add-Finding $runtimeGate "script.undeclared-env" "Install script references undeclared env '$($match.Groups[1].Value)'." $scriptName }
        }
    }

    foreach ($capability in (@(Values $contract.provides.api) + @(Values $contract.provides.db))) {
        if ($capability -is [string]) { continue }
        $sideEffect = ($capability.dbWrite -eq $true -or $capability.fileWrite -eq $true -or $capability.externalCall -eq $true)
        if (-not $sideEffect -and (Has-Property $capability 'sideEffects')) {
            $sideEffectText = ($capability.sideEffects | ConvertTo-Json -Compress -Depth 10)
            $sideEffect = $sideEffectText -match '(?i)db.?write|file.?write|external.?call'
        }
        if ($sideEffect) {
            $missingDocs = @('input','output','errors','sideEffects' | Where-Object { -not (Has-Documentation $capability $_) })
            if ($missingDocs.Count -gt 0) { Add-Finding $runtimeGate "capability.io-review" "Side-effecting capability '$(Get-CapabilityName $capability)' lacks: $($missingDocs -join ', ')." $missingDocs "warning" }
        }
    }

    $platformMajor = if ((Has-Property $installManifest 'platformMajor')) { [string]$installManifest.platformMajor } else { ([string]$centralManifest.manifestVersion).Split('.')[0] }
    $centralMajor = ([string]$centralManifest.manifestVersion).Split('.')[0]
    if ($platformMajor -ne $centralMajor) {
        if (Has-CompleteAdapter $definition) { $compatibilityGate.status = 'pass_with_adapter'; $compatibilityGate.evidence.Add([ordered]@{ platformMajor = $platformMajor; centralMajor = $centralMajor; adapter = $definition.compatibility.adapter.name }) }
        else { Add-Finding $compatibilityGate "platform.incompatible" "Platform major $platformMajor is incompatible with central major $centralMajor and no complete adapter/migration/rollback is declared." }
    }

    if (-not (Has-Property $contract 'admissionEvidence') -or $contract.admissionEvidence.rerunnable -ne $true -or @(Values $contract.admissionEvidence.negativeTests).Count -eq 0) {
        Add-Finding $verificationGate "evidence.missing" "Admission evidence must be rerunnable and include at least one negative test; Kit-owned tests alone are not sufficient."
    }

    if ($preflight.status -eq 'pass' -and $configGate.status -ne 'fail') {
        $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("external-kit-admission-" + [guid]::NewGuid().ToString('N'))
        try {
            New-Item -ItemType Directory -Force (Join-Path $tempRoot 'assembly'), (Join-Path $tempRoot 'kits') | Out-Null
            $syntheticManifest = [ordered]@{ manifestVersion = $centralManifest.manifestVersion; name = 'external-admission'; defaultDatabaseRecommendation = $centralManifest.defaultDatabaseRecommendation; kits = @($centralManifest.kits) + @($definition) }
            $syntheticManifest | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 (Join-Path $tempRoot 'manifest.json')
            [ordered]@{ recipeVersion = '0.1.0'; name = 'external-admission'; sourceManifest = 'manifest.json'; database = [ordered]@{ engine = 'postgresql' }; enabledKits = @([string]$definition.id) } | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $tempRoot 'recipe.json')
            & (Join-Path $ProjectRoot 'tools\resolve-recipe.ps1') -ProjectRoot $tempRoot -ManifestPath 'manifest.json' -RecipePath 'recipe.json' -OutputPath 'assembly\resolved.json'
            $plan = Read-Json (Join-Path $tempRoot 'assembly\resolved.json')
            if (@(Values $plan.missing).Count -gt 0) {
                foreach ($missing in Values $plan.missing) { Add-Finding $assemblyGate "dependency.invalid" ([string]$missing.reason) $missing }
            } else {
                foreach ($kitId in Values $plan.resolvedKitOrder) {
                    $kitDirectory = Join-Path $tempRoot "kits\$kitId"; New-Item -ItemType Directory -Force $kitDirectory | Out-Null
                    if ($kitId -eq [string]$definition.id) {
                        $installManifest | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 (Join-Path $kitDirectory 'manifest.json')
                        $contract | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 (Join-Path $kitDirectory 'kit.contract.json')
                    } else {
                        Copy-Item -LiteralPath (Join-Path $ProjectRoot "kits\$kitId\manifest.json") -Destination $kitDirectory
                        Copy-Item -LiteralPath (Join-Path $ProjectRoot "kits\$kitId\kit.contract.json") -Destination $kitDirectory
                    }
                }
                try { & (Join-Path $ProjectRoot 'tools\validate-kit-contracts.ps1') -ProjectRoot $tempRoot -ResolvedPlanPath 'assembly\resolved.json' -OutputPath 'assembly\contracts.json' } catch { Add-Finding $assemblyGate "contract.dry-run" $_.Exception.Message }
                try { & (Join-Path $ProjectRoot 'tools\generate-assembly-ir.ps1') -ProjectRoot $tempRoot -ResolvedPlanPath 'assembly\resolved.json' -ManifestPath 'manifest.json' -OutputPath 'assembly\ir.json'; $null = Read-Json (Join-Path $tempRoot 'assembly\ir.json') } catch { Add-Finding $assemblyGate "assembly-ir.dry-run" $_.Exception.Message }
                $assemblyGate.evidence.Add([ordered]@{ resolver = 'pass'; assemblyIr = if ($assemblyGate.status -eq 'fail') { 'fail' } else { 'pass' }; resolvedKitOrder = @($plan.resolvedKitOrder) })
            }
        } catch { Add-Finding $assemblyGate "resolver.dry-run" $_.Exception.Message }
        finally {
            if ($tempRoot -and $tempRoot.StartsWith([IO.Path]::GetTempPath(), [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $tempRoot)) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
        }
    }
}

$hasFailure = $preflight.status -eq 'fail' -or @($gates | Where-Object { $_.status -eq 'fail' }).Count -gt 0
$hasReview = @($gates | Where-Object { $_.status -eq 'warning' }).Count -gt 0
$hasAdapter = @($gates | Where-Object { $_.status -eq 'pass_with_adapter' }).Count -gt 0
$verdict = if ($hasFailure) { 'rejected' } elseif ($hasReview) { 'needs_review' } elseif ($hasAdapter) { 'accepted_with_adapter' } else { 'accepted' }

$report = [pscustomobject][ordered]@{
    reportVersion = '1.0'; validatorVersion = $validatorVersion
    package = [ordered]@{ kit = if ($definition) { [string]$definition.id } else { $null }; version = if ($installManifest -and (Has-Property $installManifest 'version')) { [string]$installManifest.version } else { $null }; sha256 = $packageHash; source = '.' }
    verdict = $verdict; preflight = $preflight; gates = $gates
    plannedChanges = [ordered]@{ catalogEntries = if ($definition) { @([string]$definition.id) } else { @() }; files = if ($root) { @($preflight.inventory.path) } else { @() }; routes = if ($definition) { @(Get-RouteKeys $definition $contract) } else { @() }; models = if ($definition) { @(Values $definition.database.models | ForEach-Object { Get-ModelName $_ }) } else { @() }; tables = if ($definition) { @(Get-TableNames $definition.database) } else { @() }; config = if ($definition) { @(Get-ConfigKeys $definition $installManifest) } else { @() } }
}

if ($OutputPath) {
    $fullOutputPath = if ([IO.Path]::IsPathRooted($OutputPath)) { $OutputPath } else { Join-Path $ProjectRoot $OutputPath }
    $outputDirectory = Split-Path -Parent $fullOutputPath
    if ($outputDirectory -and -not (Test-Path -LiteralPath $outputDirectory)) { New-Item -ItemType Directory -Force $outputDirectory | Out-Null }
    $report | ConvertTo-Json -Depth 80 | Set-Content -Encoding UTF8 -LiteralPath $fullOutputPath
}

if ($PassThru) { $report } else { $report | ConvertTo-Json -Depth 80 }
