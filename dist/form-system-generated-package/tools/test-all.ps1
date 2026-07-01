param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"

function Run-Step([string]$Name, [scriptblock]$Script) {
    Write-Host "== $Name =="
    & $Script
}

Run-Step "JSON syntax" { & (Join-Path $ProjectRoot "tools\validate-json.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Recipe validation full" { & (Join-Path $ProjectRoot "tools\validate-recipe.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Recipe validation MVP" {
    & (Join-Path $ProjectRoot "tools\validate-recipe.ps1") `
        -ProjectRoot $ProjectRoot `
        -RecipePath "assembly\mvp-import-flow.recipe.json"
}
Run-Step "Resolver" { & (Join-Path $ProjectRoot "tools\test-resolver.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Backend registry full" { & (Join-Path $ProjectRoot "tools\generate-backend-registry.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Backend registry MVP" {
    & (Join-Path $ProjectRoot "tools\generate-backend-registry.ps1") `
        -ProjectRoot $ProjectRoot `
        -ResolvedPlanPath "assembly\mvp-resolved-plan.json" `
        -OutputDirectory "assembly\backend-registry-mvp"
}
Run-Step "Python registry compile" {
    $python = "C:\Users\gslab\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    & $python -m py_compile `
        (Join-Path $ProjectRoot "assembly\backend-registry\backend_router_registry.py") `
        (Join-Path $ProjectRoot "assembly\backend-registry-mvp\backend_router_registry.py")
}
Run-Step "Frontend registry" { & (Join-Path $ProjectRoot "tools\generate-frontend-registry.ps1") -ProjectRoot $ProjectRoot }
Run-Step "DB plan" { & (Join-Path $ProjectRoot "tools\generate-db-plan.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Assembly IR" {
    & (Join-Path $ProjectRoot "tools\generate-assembly-ir.ps1") -ProjectRoot $ProjectRoot
    Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "assembly\assembly-ir.json") | ConvertFrom-Json | Out-Null
}
Run-Step "Daihui schema plan" {
    $ir = Get-Content -Raw -Encoding UTF8 (Join-Path $ProjectRoot "assembly\assembly-ir.json") | ConvertFrom-Json
    if (-not $ir.database.baselines.daihuiFormSchema) { throw "Assembly IR is missing Daihui schema baseline data" }
    if (@($ir.database.physicalFirstStorage.decisions | Where-Object { ([string]$_.subject).StartsWith("daihui.") }).Count -eq 0) {
        throw "Assembly IR did not emit Daihui storage decisions"
    }
}
Run-Step "Registry generation from Assembly IR" {
    & (Join-Path $ProjectRoot "tools\generate-backend-registry.ps1") `
        -ProjectRoot $ProjectRoot `
        -IRPath "assembly\assembly-ir.json"
    & (Join-Path $ProjectRoot "tools\generate-frontend-registry.ps1") `
        -ProjectRoot $ProjectRoot `
        -IRPath "assembly\assembly-ir.json"
    $python = "C:\Users\gslab\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    & $python -m py_compile (Join-Path $ProjectRoot "assembly\backend-registry\backend_router_registry.py")
}
Run-Step "Entitlement plan" { & (Join-Path $ProjectRoot "tools\generate-entitlement-plan.ps1") -ProjectRoot $ProjectRoot }
Run-Step "MVP extraction" { & (Join-Path $ProjectRoot "tools\extract-mvp-flow.ps1") -ProjectRoot $ProjectRoot }
Run-Step "UploadPage refactor" { & (Join-Path $ProjectRoot "tools\test-upload-page-refactor.ps1") -ProjectRoot $ProjectRoot }
Run-Step "MVP extraction dry-run" { & (Join-Path $ProjectRoot "tools\extract-mvp-flow.ps1") -ProjectRoot $ProjectRoot -DryRun | Out-Null }
Run-Step "GUI static smoke" { & (Join-Path $ProjectRoot "tools\test-gui-static.ps1") -ProjectRoot $ProjectRoot }
Run-Step "GUI recipe export" { & (Join-Path $ProjectRoot "tools\test-gui-recipe-export.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Baseline contracts" {
    $reqBaseline = Join-Path $ProjectRoot "assembly\baselines\default-requirements.baseline.json"
    $dbBaseline  = Join-Path $ProjectRoot "assembly\baselines\default-db-schema.baseline.json"
    if (-not (Test-Path $reqBaseline)) { throw "Missing: $reqBaseline" }
    if (-not (Test-Path $dbBaseline))  { throw "Missing: $dbBaseline" }
    $req = Get-Content -Raw -Encoding UTF8 $reqBaseline | ConvertFrom-Json
    if ($req.python.packages.Count -eq 0) { throw "requirements baseline has no packages" }
    $db = Get-Content -Raw -Encoding UTF8 $dbBaseline | ConvertFrom-Json
    if ($db.tables.PSObject.Properties.Name.Count -eq 0) { throw "db schema baseline has no tables" }
}
Run-Step "Assemble generated system" {
    $assembleArgs = @{
        ProjectRoot = $ProjectRoot
        CreateZip = $true
    }
    if ($SkipFrontendBuild) {
        $assembleArgs.SkipFrontendBuild = $true
    }
    & (Join-Path $ProjectRoot "tools\assemble-system.ps1") @assembleArgs
}
Run-Step "Frontend production build" {
    if ($SkipFrontendBuild) {
        Write-Host "  SKIPPED frontend production build because -SkipFrontendBuild was provided"
        return
    }

    $distIndex = Join-Path $ProjectRoot "dist\generated-system\frontend\dist\index.html"
    if (-not (Test-Path $distIndex)) { throw "Frontend build missing: dist\generated-system\frontend\dist\index.html" }
    Write-Host "  OK dist\generated-system\frontend\dist\index.html present"
}
Run-Step "Kit install plan" {
    $irPath = Join-Path $ProjectRoot "assembly\assembly-ir.json"
    $generatedIrPath = Join-Path $ProjectRoot "dist\generated-system\assembly\assembly-ir.json"
    $kitsPath = Join-Path $ProjectRoot "dist\generated-system\kits"
    $runnerPath = Join-Path $ProjectRoot "dist\generated-system\scripts\run-kit-installs.ps1"
    $planPath = Join-Path $ProjectRoot "dist\generated-system\kitInstallPlan.json"

    $ir = Get-Content -Raw -Encoding UTF8 $irPath | ConvertFrom-Json
    if (@($ir.kitInstallPlan).Count -eq 0) {
        throw "assembly-ir.json has an empty kitInstallPlan"
    }
    if (-not (Test-Path $generatedIrPath)) {
        throw "Generated assembly-ir.json is missing: $generatedIrPath"
    }
    $generatedIr = Get-Content -Raw -Encoding UTF8 $generatedIrPath | ConvertFrom-Json
    if (@($generatedIr.kitInstallPlan).Count -eq 0) {
        throw "Generated assembly-ir.json has an empty kitInstallPlan"
    }
    if (-not (Test-Path $kitsPath)) {
        throw "Generated kits directory is missing: $kitsPath"
    }
    if (-not (Test-Path $runnerPath)) {
        throw "Generated kit install runner is missing: $runnerPath"
    }
    if (-not (Test-Path $planPath)) {
        throw "Generated kitInstallPlan.json is missing: $planPath"
    }
    $plan = Get-Content -Raw -Encoding UTF8 $planPath | ConvertFrom-Json
    if (@($plan).Count -eq 0) {
        throw "kitInstallPlan.json is empty"
    }
}
Run-Step "Dependency files" { & (Join-Path $ProjectRoot "tools\test-dependency-files.ps1") -ProjectRoot $ProjectRoot }
Run-Step "DB bootstrap" { & (Join-Path $ProjectRoot "tools\test-db-bootstrap.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Generated start validation" { & (Join-Path $ProjectRoot "tools\test-generated-start.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Process supervision" { & (Join-Path $ProjectRoot "tools\test-process-supervision.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Validate generated system" { & (Join-Path $ProjectRoot "tools\validate-generated-system.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Generated system zip" {
    if (-not (Test-Path (Join-Path $ProjectRoot "dist\generated-system.zip"))) {
        throw "generated-system.zip was not created"
    }
}
Run-Step "Package folder" { & (Join-Path $ProjectRoot "tools\package-system.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Validate package folder" { & (Join-Path $ProjectRoot "tools\validate-package-folder.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Client deploy package" { & (Join-Path $ProjectRoot "tools\package-client-deploy.ps1") -ProjectRoot $ProjectRoot -RecipeName gui-all-kits -SkipZip }
Run-Step "Client deploy variants" { & (Join-Path $ProjectRoot "tools\test-client-deploy-variants.ps1") -ProjectRoot $ProjectRoot }

Write-Host "ALL TESTS PASSED"
