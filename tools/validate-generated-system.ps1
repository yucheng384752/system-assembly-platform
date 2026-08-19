param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$GeneratedSystemDirectory = "dist\generated-system"
)

$ErrorActionPreference = "Stop"

$root = Join-Path $ProjectRoot $GeneratedSystemDirectory
$requiredPaths = @(
    "backend\app\main.py",
    "backend\app\core\backend_router_registry.py",
    "frontend",
    "scripts\check-prerequisites.ps1",
    "scripts\check-db.ps1",
    "scripts\install.ps1",
    "scripts\migrate.ps1",
    "scripts\smoke-start.ps1",
    "scripts\status.ps1",
    "scripts\stop.ps1",
    "scripts\restart.ps1",
    "scripts\start.ps1",
    ".env.example",
    "dependency-manifest.json",
    "dependency-plan.json",
    "db-bootstrap-plan.json",
    "backend\app\core\generated_db_bootstrap.py",
    "backend\app\models\__init__.py",
    "backend\requirements.txt",
    "frontend\package.json",
    "package-manifest.json",
    "README.md"
)

$missing = New-Object System.Collections.Generic.List[string]
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path (Join-Path $root $relativePath))) {
        $missing.Add($relativePath)
    }
}

if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Error "Missing generated system path: $_" }
    throw "Generated system validation failed"
}

$frontendPackagePath = Join-Path $root "frontend\package.json"
$frontendLockPath = Join-Path $root "frontend\package-lock.json"
if (Test-Path $frontendPackagePath) {
    if (-not (Test-Path $frontendLockPath)) {
        Write-Error "Missing generated system path: frontend\package-lock.json"
        throw "Generated system validation failed"
    }

    $frontendPackageJson = Get-Content -Raw -Encoding UTF8 -LiteralPath $frontendPackagePath | ConvertFrom-Json
    $frontendLockText = Get-Content -Raw -Encoding UTF8 -LiteralPath $frontendLockPath
    foreach ($dep in $frontendPackageJson.dependencies.PSObject.Properties) {
        $needle = '"' + $dep.Name + '": "' + $dep.Value + '"'
        if (-not $frontendLockText.Contains($needle)) {
            throw "frontend package-lock.json dependency mismatch: $($dep.Name)"
        }
    }
    foreach ($dep in $frontendPackageJson.devDependencies.PSObject.Properties) {
        $needle = '"' + $dep.Name + '": "' + $dep.Value + '"'
        if (-not $frontendLockText.Contains($needle)) {
            throw "frontend package-lock.json devDependency mismatch: $($dep.Name)"
        }
    }
}

function Resolve-FrontendImport([string]$ImporterPath, [string]$ImportValue) {
    if (-not $ImportValue.StartsWith(".")) {
        return $null
    }

    $basePath = Join-Path (Split-Path -Parent $ImporterPath) $ImportValue
    $candidates = @(
        $basePath,
        "$basePath.ts",
        "$basePath.tsx",
        "$basePath.js",
        "$basePath.jsx",
        "$basePath.css",
        "$basePath.json",
        (Join-Path $basePath "index.ts"),
        (Join-Path $basePath "index.tsx"),
        (Join-Path $basePath "index.js"),
        (Join-Path $basePath "index.jsx")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

$frontendSrc = Join-Path $root "frontend\src"
if (Test-Path $frontendSrc) {
    $importPattern = 'import\s+(?:[^''";]+?\s+from\s+)?["'']([^"'']+)["'']'
    $missingImports = New-Object System.Collections.Generic.List[string]

    Get-ChildItem -LiteralPath $frontendSrc -Recurse -File -Include *.ts,*.tsx,*.js,*.jsx | ForEach-Object {
        $filePath = $_.FullName
        $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $filePath
        if ($null -eq $content) {
            $content = ""
        }
        foreach ($match in [regex]::Matches($content, $importPattern)) {
            $importValue = [string]$match.Groups[1].Value
            if ($importValue.StartsWith(".") -and -not (Resolve-FrontendImport $filePath $importValue)) {
                $relativeImporter = $filePath.Substring($root.Length + 1)
                $missingImports.Add("${relativeImporter}: $importValue")
            }
        }
    }

    if ($missingImports.Count -gt 0) {
        $missingImports | ForEach-Object { Write-Error "Missing frontend import: $_" }
        throw "Generated system frontend import validation failed"
    }
}

Write-Host "OK $GeneratedSystemDirectory"
