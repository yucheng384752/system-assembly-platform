param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$SystemDirectory = "dist\generated-system"
)

$ErrorActionPreference = "Stop"

# Pinned production versions — update here when bumping deps.
$PYTHON_VERSIONS = @{
    "fastapi"            = "0.115.0"
    "uvicorn[standard]"  = "0.30.6"
    "sqlalchemy"         = "2.0.36"
    "pydantic"           = "2.9.2"
    "pydantic-settings"  = "2.5.2"
    "starlette"          = "0.40.0"
    "structlog"          = "24.4.0"
    "pandas"             = "2.2.3"
    "httpx"              = "0.27.2"
    "python-dotenv"      = "1.0.1"
    "python-multipart"   = "0.0.12"
    "asyncpg"            = "0.29.0"
    "openpyxl"           = "3.1.5"
}

$FRONTEND_VERSIONS = @{
    "react"                          = "18.3.1"
    "react-dom"                      = "18.3.1"
    "react-i18next"                  = "15.0.2"
    "i18next"                        = "23.15.2"
    "i18next-browser-languagedetector" = "8.0.0"
    "lucide-react"                   = "0.460.0"
    "@vitejs/plugin-react"           = "4.3.3"
    "vite"                           = "6.0.5"
    "typescript"                     = "5.7.2"
    "@types/react"                   = "18.3.12"
    "@types/react-dom"               = "18.3.1"
}

function Get-PythonVersion([string]$PackageName) {
    if ($PYTHON_VERSIONS.ContainsKey($PackageName)) { return $PYTHON_VERSIONS[$PackageName] }
    return "latest"
}

function Get-FrontendVersion([string]$PackageName) {
    if ($FRONTEND_VERSIONS.ContainsKey($PackageName)) { return $FRONTEND_VERSIONS[$PackageName] }
    return "latest"
}

function Get-TopLevelPythonImports([string]$BackendPath) {
    $imports = New-Object System.Collections.Generic.HashSet[string]
    if (-not (Test-Path $BackendPath)) {
        return $imports
    }

    Get-ChildItem -LiteralPath $BackendPath -Recurse -File -Filter *.py | ForEach-Object {
        $content = Get-Content -Raw -Encoding UTF8 $_.FullName
        foreach ($match in [regex]::Matches($content, "(?m)^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_\.]*)")) {
            $topLevel = $match.Groups[1].Value.Split(".")[0]
            [void]$imports.Add($topLevel)
        }
    }
    return $imports
}

function Get-FrontendPackageImports([string]$FrontendPath) {
    $imports = New-Object System.Collections.Generic.HashSet[string]
    if (-not (Test-Path $FrontendPath)) {
        return $imports
    }

    Get-ChildItem -LiteralPath $FrontendPath -Recurse -File -Include *.ts,*.tsx,*.js,*.jsx | ForEach-Object {
        $content = Get-Content -Raw -Encoding UTF8 $_.FullName
        foreach ($match in [regex]::Matches($content, "from\s+['""]([^'""]+)['""]|import\s*\(\s*['""]([^'""]+)['""]\s*\)")) {
            $specifier = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
            if ($specifier.StartsWith(".") -or $specifier.StartsWith("/")) {
                continue
            }
            $packageName = $specifier
            if ($specifier.StartsWith("@")) {
                $parts = $specifier.Split("/")
                if ($parts.Length -ge 2) {
                    $packageName = "$($parts[0])/$($parts[1])"
                }
            } else {
                $packageName = $specifier.Split("/")[0]
            }
            [void]$imports.Add($packageName)
        }
    }
    return $imports
}

function Add-IfImported(
    [System.Collections.Generic.HashSet[string]]$Imports,
    [System.Collections.Generic.List[string]]$Requirements,
    [string]$ImportName,
    [string]$RequirementName
) {
    if ($Imports.Contains($ImportName) -and -not $Requirements.Contains($RequirementName)) {
        $Requirements.Add($RequirementName)
    }
}

$systemPath = Join-Path $ProjectRoot $SystemDirectory
$backendPath = Join-Path $systemPath "backend"
$frontendPath = Join-Path $systemPath "frontend"

if (-not (Test-Path $systemPath)) {
    throw "System directory not found: $systemPath"
}

$pythonImports = Get-TopLevelPythonImports $backendPath
$requirementNames = New-Object System.Collections.Generic.List[string]

Add-IfImported $pythonImports $requirementNames "fastapi" "fastapi"
Add-IfImported $pythonImports $requirementNames "uvicorn" "uvicorn[standard]"
Add-IfImported $pythonImports $requirementNames "sqlalchemy" "sqlalchemy"
Add-IfImported $pythonImports $requirementNames "pydantic" "pydantic"
Add-IfImported $pythonImports $requirementNames "pydantic_settings" "pydantic-settings"
Add-IfImported $pythonImports $requirementNames "starlette" "starlette"
Add-IfImported $pythonImports $requirementNames "structlog" "structlog"
Add-IfImported $pythonImports $requirementNames "pandas" "pandas"
Add-IfImported $pythonImports $requirementNames "httpx" "httpx"
Add-IfImported $pythonImports $requirementNames "dotenv" "python-dotenv"

$backendContent = ""
if (Test-Path $backendPath) {
    $backendContent = (Get-ChildItem -LiteralPath $backendPath -Recurse -File -Filter *.py | ForEach-Object {
        Get-Content -Raw -Encoding UTF8 $_.FullName
    }) -join "`n"
}

if ($backendContent.Contains("UploadFile") -and -not $requirementNames.Contains("python-multipart")) {
    $requirementNames.Add("python-multipart")
}
if ($backendContent.Contains("postgresql+asyncpg") -or $backendContent.Contains("create_async_engine")) {
    if (-not $requirementNames.Contains("asyncpg")) {
        $requirementNames.Add("asyncpg")
    }
}
if ($backendContent.Contains("read_excel") -or $backendContent.Contains("Excel")) {
    if (-not $requirementNames.Contains("openpyxl")) {
        $requirementNames.Add("openpyxl")
    }
}

# Build pinned requirement lines (e.g. "fastapi==0.115.0")
$requirementLines = ($requirementNames | Sort-Object) | ForEach-Object {
    $ver = Get-PythonVersion $_
    if ($ver -eq "latest") { $_ } else { "$_==$ver" }
}

$requirementsPath = Join-Path $backendPath "requirements.txt"
$requirementLines | Set-Content -Encoding UTF8 $requirementsPath

$frontendImports = Get-FrontendPackageImports $frontendPath
$dependencies = [ordered]@{}
foreach ($packageName in @("react", "react-dom", "react-i18next", "i18next", "i18next-browser-languagedetector", "lucide-react")) {
    if ($frontendImports.Contains($packageName)) {
        $dependencies[$packageName] = Get-FrontendVersion $packageName
    }
}
if (-not $dependencies.Contains("react")) {
    $dependencies["react"] = Get-FrontendVersion "react"
}
if (-not $dependencies.Contains("react-dom")) {
    $dependencies["react-dom"] = Get-FrontendVersion "react-dom"
}

$devDependencies = [ordered]@{
    "@vitejs/plugin-react" = Get-FrontendVersion "@vitejs/plugin-react"
    "vite"                 = Get-FrontendVersion "vite"
    "typescript"           = Get-FrontendVersion "typescript"
    "@types/react"         = Get-FrontendVersion "@types/react"
    "@types/react-dom"     = Get-FrontendVersion "@types/react-dom"
}

$packageJson = [ordered]@{
    private = $true
    type = "module"
    scripts = [ordered]@{
        dev = "vite"
        build = "tsc -b && vite build"
        preview = "vite preview"
    }
    dependencies = $dependencies
    devDependencies = $devDependencies
}

$packageJsonPath = Join-Path $frontendPath "package.json"
$packageJson | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $packageJsonPath

$plan = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    systemDirectory = $SystemDirectory
    backend = [ordered]@{
        source = "inferred-from-python-imports"
        imports = @($pythonImports | Sort-Object)
        requirementsPath = "backend\requirements.txt"
        requirements = @($requirementLines)
    }
    frontend = [ordered]@{
        source = "inferred-from-frontend-imports"
        imports = @($frontendImports | Sort-Object)
        packageJsonPath = "frontend\package.json"
        dependencies = $dependencies
        devDependencies = $devDependencies
    }
}

$plan | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $systemPath "dependency-plan.json")

Write-Host "Dependency files generated in $SystemDirectory"
