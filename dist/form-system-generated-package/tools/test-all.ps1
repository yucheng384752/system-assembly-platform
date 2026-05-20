param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
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
Run-Step "Entitlement plan" { & (Join-Path $ProjectRoot "tools\generate-entitlement-plan.ps1") -ProjectRoot $ProjectRoot }
Run-Step "MVP extraction" { & (Join-Path $ProjectRoot "tools\extract-mvp-flow.ps1") -ProjectRoot $ProjectRoot }
Run-Step "UploadPage refactor" { & (Join-Path $ProjectRoot "tools\test-upload-page-refactor.ps1") -ProjectRoot $ProjectRoot }
Run-Step "MVP extraction dry-run" { & (Join-Path $ProjectRoot "tools\extract-mvp-flow.ps1") -ProjectRoot $ProjectRoot -DryRun | Out-Null }
Run-Step "GUI static smoke" { & (Join-Path $ProjectRoot "tools\test-gui-static.ps1") -ProjectRoot $ProjectRoot }
Run-Step "GUI recipe export" { & (Join-Path $ProjectRoot "tools\test-gui-recipe-export.ps1") -ProjectRoot $ProjectRoot }
Run-Step "Assemble generated system" { & (Join-Path $ProjectRoot "tools\assemble-system.ps1") -ProjectRoot $ProjectRoot -CreateZip }
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

Write-Host "ALL TESTS PASSED"
