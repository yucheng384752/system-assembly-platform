param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"
$validator = Join-Path $ProjectRoot 'tools\validate-external-kit.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("external-kit-validation-tests-" + [guid]::NewGuid().ToString('N'))

function Clone($Value) {
    $Value | ConvertTo-Json -Depth 50 | ConvertFrom-Json
}

function Add-Property($Object, [string]$Name, $Value) {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force
}

function New-Fixture([string]$Name, [scriptblock]$Change) {
    $path = Join-Path $testRoot $Name
    New-Item -ItemType Directory -Force (Join-Path $path 'src\app\core') | Out-Null
    Set-Content -Encoding UTF8 -LiteralPath (Join-Path $path 'src\app\core\example.py') -Value '# static fixture source'

    $definition = [pscustomobject][ordered]@{
        id = "external-$Name-kit"
        displayName = "External $Name"
        category = 'integration'
        businessCapability = 'Static admission fixture.'
        dependencies = @()
        frontend = [pscustomobject]@{}
        backend = [pscustomobject][ordered]@{ core = @('app/core/example.py'); models = @(); routerRegistrations = @() }
        database = [pscustomobject][ordered]@{ owner = "external-$Name-kit"; models = @(); tables = @() }
    }
    $manifest = [pscustomobject][ordered]@{
        kit = $definition.id
        version = '1.0.0'
        displayName = $definition.displayName
        installOrder = 500
        requires = @('python')
        runtimeEnv = @()
        scripts = [pscustomobject]@{}
        platformMajor = '0'
    }
    $contract = [pscustomobject][ordered]@{
        kit = $definition.id
        provides = [pscustomobject][ordered]@{ api = @(); db = @() }
        consumes = [pscustomobject][ordered]@{ api = @(); db = @() }
        admissionEvidence = [pscustomobject][ordered]@{ rerunnable = $true; negativeTests = @('rejects-invalid-input') }
    }

    & $Change $path $definition $manifest $contract
    $definition | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $path 'kit.definition.json')
    $manifest | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $path 'manifest.json')
    $contract | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $path 'kit.contract.json')
    $path
}

function Validate([string]$Path) {
    & $validator -PackagePath $Path -ProjectRoot $ProjectRoot -PassThru
}

function Assert-Verdict([string]$Name, $Report, [string]$Expected) {
    if ($Report.verdict -ne $Expected) {
        $summary = @($Report.preflight.findings + @($Report.gates | ForEach-Object { $_.findings })) | ConvertTo-Json -Depth 20 -Compress
        throw "$Name expected '$Expected', got '$($Report.verdict)': $summary"
    }
    Write-Host "PASS $Name -> $Expected"
}

function Assert-Finding($Report, [string]$Code) {
    $codes = @($Report.preflight.findings.code) + @($Report.gates | ForEach-Object { $_.findings.code })
    if ($codes -notcontains $Code) { throw "Expected finding '$Code', got: $($codes -join ', ')" }
}

try {
    New-Item -ItemType Directory -Force $testRoot | Out-Null

    # Test Plan row 1: a clean package is accepted; its side-effecting variant is needs_review.
    $valid = New-Fixture 'valid' { param($path, $definition, $manifest, $contract) }
    Assert-Verdict '1a clean external kit' (Validate $valid) 'accepted'
    $review = New-Fixture 'gate4-review' {
        param($path, $definition, $manifest, $contract)
        $contract.provides.api = @([pscustomobject][ordered]@{ capability = 'external.review'; method = 'POST'; path = '/api/external-review'; externalCall = $true })
    }
    $reviewReport = Validate $review
    Assert-Verdict '1b undocumented side effect' $reviewReport 'needs_review'
    Assert-Finding $reviewReport 'capability.io-review'
    $schema = New-Fixture 'schema-wrapper' {
        param($path, $definition, $manifest, $contract)
        $definition.PSObject.Properties.Remove('displayName')
    }
    $schemaReport = Validate $schema
    Assert-Verdict '1c wrapper schema rejection' $schemaReport 'rejected'
    Assert-Finding $schemaReport 'definition.schema'

    $escape = New-Fixture 'path-escape' {
        param($path, $definition, $manifest, $contract)
        $definition.backend.core = @('../outside.py')
    }
    $escapeReport = Validate $escape
    Assert-Verdict '2 source path escape' $escapeReport 'rejected'
    Assert-Finding $escapeReport 'source.path-escape'

    $collision = New-Fixture 'collision' {
        param($path, $definition, $manifest, $contract)
        $definition.backend.core += 'app/core/missing.py'
        $definition.database.models = @('Tenant')
        $definition.database.tables = @('tenants')
        Add-Property $definition 'config' ([pscustomobject]@{ PDF_SERVER_URL = [pscustomobject]@{ required = $true } })
        $contract.provides.api = @([pscustomobject][ordered]@{ capability = 'external.collision'; method = 'POST'; path = '/api/auth/me/password' })
    }
    $collisionReport = Validate $collision
    Assert-Verdict '3 central source/route/model/table/config collision' $collisionReport 'rejected'
    Assert-Finding $collisionReport 'source.missing'
    Assert-Finding $collisionReport 'route.collision'
    Assert-Finding $collisionReport 'model.collision'
    Assert-Finding $collisionReport 'table.collision'
    Assert-Finding $collisionReport 'config.collision'

    $dependency = New-Fixture 'dependency' {
        param($path, $definition, $manifest, $contract)
        $definition.dependencies = @('missing-kit')
    }
    $dependencyReport = Validate $dependency
    Assert-Verdict '4 unknown dependency' $dependencyReport 'rejected'
    Assert-Finding $dependencyReport 'dependency.invalid'

    $tenant = New-Fixture 'tenant' {
        param($path, $definition, $manifest, $contract)
        New-Item -ItemType Directory -Force (Join-Path $path 'src\app\models') | Out-Null
        Set-Content -Encoding UTF8 -LiteralPath (Join-Path $path 'src\app\models\external_record.py') -Value '# static fixture model'
        $definition.backend.models = @('app/models/external_record.py')
        $definition.database.models = @('ExternalRecord')
        $contract.provides.db = @([pscustomobject][ordered]@{ capability = 'db.external.record'; model = 'ExternalRecord'; tenantScoped = $false })
    }
    $tenantReport = Validate $tenant
    Assert-Verdict '5 missing tenant boundary' $tenantReport 'rejected'
    Assert-Finding $tenantReport 'tenant.boundary-missing'

    $runtime = New-Fixture 'runtime' {
        param($path, $definition, $manifest, $contract)
        Add-Property $manifest.scripts 'windows' 'install.ps1'
        Set-Content -Encoding UTF8 -LiteralPath (Join-Path $path 'install.ps1') -Value 'Invoke-WebRequest https://example.invalid/tool; Write-Host $env:UNLISTED_TOKEN'
    }
    $runtimeReport = Validate $runtime
    Assert-Verdict '6 unsafe install script declaration' $runtimeReport 'rejected'
    Assert-Finding $runtimeReport 'script.network'
    Assert-Finding $runtimeReport 'script.undeclared-env'

    $adapter = New-Fixture 'adapter' {
        param($path, $definition, $manifest, $contract)
        $manifest.platformMajor = '9'
        Add-Property $definition 'compatibility' ([pscustomobject][ordered]@{ adapter = [pscustomobject][ordered]@{ name = 'v9-to-v0'; migration = 'migrations/forward.sql'; rollback = 'migrations/rollback.sql' } })
    }
    Assert-Verdict '7 incompatible platform with complete adapter' (Validate $adapter) 'accepted_with_adapter'

    $evidence = New-Fixture 'evidence' {
        param($path, $definition, $manifest, $contract)
        $contract.PSObject.Properties.Remove('admissionEvidence')
        New-Item -ItemType Directory -Force (Join-Path $path 'tests') | Out-Null
        Set-Content -Encoding UTF8 -LiteralPath (Join-Path $path 'tests\claimed-pass.txt') -Value 'Kit-owned tests pass.'
    }
    $evidenceReport = Validate $evidence
    Assert-Verdict '8 Kit-owned tests without admission evidence' $evidenceReport 'rejected'
    Assert-Finding $evidenceReport 'evidence.missing'

    $duplicateDb = New-Fixture 'duplicate-db' {
        param($path, $definition, $manifest, $contract)
        $contract.provides.db = @([pscustomobject][ordered]@{ capability = 'db.tables.resolve' })
    }
    $duplicateDbReport = Validate $duplicateDb
    Assert-Verdict '9 duplicate DB capability provider' $duplicateDbReport 'rejected'
    Assert-Finding $duplicateDbReport 'db-capability.duplicate-provider'

    Write-Host 'ALL 9 EXTERNAL KIT ADMISSION FIXTURES PASSED'
} finally {
    if ($testRoot.StartsWith([IO.Path]::GetTempPath(), [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $testRoot)) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
