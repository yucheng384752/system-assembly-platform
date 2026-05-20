param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$ResolvedPlanPath = "assembly\mvp-resolved-plan.json",
    [string]$SourceSystemDirectory = "generated\mvp-import-flow\form-analysis-server",
    [string]$OutputDirectory = "dist\generated-system",
    [switch]$CreateZip
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

function New-CleanDirectory([string]$Path) {
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force $Path | Out-Null
}

function Copy-Tree([string]$Source, [string]$Destination) {
    if (-not (Test-Path $Source)) {
        throw "Source not found: $Source"
    }
    $parent = Split-Path -Parent $Destination
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Test-RelativePath([string]$Root, [string]$RelativePath) {
    return Test-Path (Join-Path $Root $RelativePath)
}

$plan = Read-JsonUtf8 (Join-Path $ProjectRoot $ResolvedPlanPath)
$sourcePath = Join-Path $ProjectRoot $SourceSystemDirectory
$outputPath = Join-Path $ProjectRoot $OutputDirectory

New-CleanDirectory $outputPath
Copy-Tree (Join-Path $sourcePath "backend") (Join-Path $outputPath "backend")
Copy-Tree (Join-Path $sourcePath "frontend") (Join-Path $outputPath "frontend")

& (Join-Path $ProjectRoot "tools\generate-dependency-files.ps1") `
    -ProjectRoot $ProjectRoot `
    -SystemDirectory $OutputDirectory

& (Join-Path $ProjectRoot "tools\generate-model-init.ps1") `
    -ProjectRoot $ProjectRoot `
    -SystemDirectory $OutputDirectory

$scriptsPath = Join-Path $outputPath "scripts"
New-Item -ItemType Directory -Force $scriptsPath | Out-Null

& (Join-Path $ProjectRoot "tools\generate-db-bootstrap.ps1") `
    -ProjectRoot $ProjectRoot `
    -SystemDirectory $OutputDirectory

$dependencyManifest = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    backend = [ordered]@{
        appEntry = "backend\app\main.py"
        requirementsTxt = Test-RelativePath $outputPath "backend\requirements.txt"
        pyprojectToml = Test-RelativePath $outputPath "backend\pyproject.toml"
        alembicIni = Test-RelativePath $outputPath "backend\alembic.ini"
        migrationDirectory = Test-RelativePath $outputPath "backend\alembic"
        installCommand = "python -m pip install -r backend\requirements.txt"
        startCommand = "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    }
    frontend = [ordered]@{
        sourceDirectory = "frontend"
        packageJson = Test-RelativePath $outputPath "frontend\package.json"
        installCommand = "npm install"
        startCommand = "npm run dev"
    }
    notes = @(
        "Dependency files are inferred from generated backend/frontend imports when source manifests are missing.",
        "If backend requirements.txt or pyproject.toml is missing, install.ps1 stops with an actionable error.",
        "If frontend package.json is missing, frontend install/start is skipped unless -WithFrontend is requested."
    )
}
$dependencyManifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $outputPath "dependency-manifest.json")

@'
param(
    [string]$Root = (Resolve-Path "$PSScriptRoot\..").Path,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

function Test-RelativePath([string]$Base, [string]$RelativePath) {
    return Test-Path (Join-Path $Base $RelativePath)
}

$checks = [ordered]@{
    backendApp = Test-RelativePath $Root "backend\app\main.py"
    backendRequirements = Test-RelativePath $Root "backend\requirements.txt"
    backendPyproject = Test-RelativePath $Root "backend\pyproject.toml"
    backendAlembic = Test-RelativePath $Root "backend\alembic.ini"
    frontendPackage = Test-RelativePath $Root "frontend\package.json"
    envExample = Test-RelativePath $Root ".env.example"
    dependencyManifest = Test-RelativePath $Root "dependency-manifest.json"
}

$summary = [ordered]@{
    root = $Root
    checks = $checks
    backendDependencyManifestPresent = ($checks.backendRequirements -or $checks.backendPyproject)
    frontendDependencyManifestPresent = $checks.frontendPackage
}

$summary | ConvertTo-Json -Depth 10

if (-not $checks.backendApp) {
    throw "Backend entry is missing: backend\app\main.py"
}

if ($Strict -and -not ($checks.backendRequirements -or $checks.backendPyproject)) {
    throw "Backend dependency manifest is missing. Add backend\requirements.txt or backend\pyproject.toml to the extracted source or dependency planner."
}

if ($Strict -and -not $checks.frontendPackage) {
    throw "Frontend dependency manifest is missing. Add frontend\package.json to enable frontend install/start."
}
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "check-prerequisites.ps1")

@'
param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$requirements = Join-Path $Root "backend\requirements.txt"
$pyproject = Join-Path $Root "backend\pyproject.toml"
$frontendPackage = Join-Path $Root "frontend\package.json"

if (Test-Path $requirements) {
    Write-Host "Installing backend dependencies from backend\requirements.txt"
    & $Python -m pip install -r $requirements
} elseif (Test-Path $pyproject) {
    Write-Host "Installing backend project from backend\pyproject.toml"
    Push-Location (Join-Path $Root "backend")
    try {
        & $Python -m pip install .
    } finally {
        Pop-Location
    }
} else {
    throw "Backend dependency manifest is missing. Add backend\requirements.txt or backend\pyproject.toml before running install."
}

if (-not $SkipFrontend) {
    if (Test-Path $frontendPackage) {
        Write-Host "Installing frontend dependencies from frontend\package.json"
        Push-Location (Join-Path $Root "frontend")
        try {
            & $Npm install
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning "frontend\package.json is missing; skipping frontend install."
    }
}

Write-Host "Install step completed."
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "install.ps1")

@'
param(
    [string]$Python = "python",
    [int]$BackendPort = 8000,
    [int]$TimeoutSeconds = 15,
    [switch]$ImportApp,
    [switch]$StartBackend
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$BackendRoot = Join-Path $Root "backend"

function Invoke-CheckedNative([scriptblock]$Command, [string]$FailureMessage) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root -Strict | Out-Host

$requiredPaths = @(
    "backend\app\main.py",
    "backend\app\models\__init__.py",
    "backend\requirements.txt",
    "frontend\package.json",
    "scripts\start.ps1"
)

foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path (Join-Path $Root $relativePath))) {
        throw "Missing smoke-start path: $relativePath"
    }
}

$pythonFiles = Get-ChildItem -LiteralPath (Join-Path $BackendRoot "app") -Recurse -Filter *.py | ForEach-Object { $_.FullName }
if ($pythonFiles.Count -eq 0) {
    throw "No backend Python files found for compile smoke."
}
Invoke-CheckedNative { & $Python -m py_compile @pythonFiles } "Backend Python compile smoke failed."

$startScript = Get-Content -Raw -Encoding UTF8 (Join-Path $Root "scripts\start.ps1")
if ($startScript -notmatch "uvicorn app\.main:app") {
    throw "scripts\start.ps1 does not start uvicorn app.main:app."
}

$result = [ordered]@{
    root = $Root
    pythonFilesCompiled = $pythonFiles.Count
    importAppRequested = [bool]$ImportApp
    startBackendRequested = [bool]$StartBackend
}

if ($ImportApp -or $StartBackend) {
    $envPath = Join-Path $Root ".env"
    $envExamplePath = Join-Path $Root ".env.example"
    if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
        Copy-Item -LiteralPath $envExamplePath -Destination $envPath
        Write-Host "Created .env from .env.example"
    }
}

if ($ImportApp) {
    Push-Location $BackendRoot
    try {
        Invoke-CheckedNative { & $Python -c "import app.main; print(app.main.app.title)" } "Generated FastAPI app import smoke failed."
    } finally {
        Pop-Location
    }
}

if ($StartBackend) {
    Push-Location $BackendRoot
    try {
        $process = Start-Process $Python -ArgumentList @(
            "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1",
            "--port", [string]$BackendPort
        ) -WindowStyle Hidden -PassThru

        try {
            $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
            $healthy = $false
            while ((Get-Date) -lt $deadline) {
                if ($process.HasExited) {
                    throw "Backend process exited early with code $($process.ExitCode)."
                }
                try {
                    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/healthz" -TimeoutSec 2
                    if ($response.status -eq "healthy") {
                        $healthy = $true
                        break
                    }
                } catch {
                    Start-Sleep -Milliseconds 500
                }
            }
            if (-not $healthy) {
                throw "Backend health endpoint did not become healthy within $TimeoutSeconds seconds."
            }
            $result.backendHealth = "healthy"
        } finally {
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
            }
        }
    } finally {
        Pop-Location
    }
}

$result | ConvertTo-Json -Depth 10
Write-Host "OK smoke-start"
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "smoke-start.ps1")

@'
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$envPath = Join-Path $Root ".env"
$envExamplePath = Join-Path $Root ".env.example"
if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created .env from .env.example"
}

$alembicIni = Join-Path $Root "backend\alembic.ini"
if (Test-Path $alembicIni) {
    Write-Host "Running Alembic migrations."
    Push-Location (Join-Path $Root "backend")
    try {
        & $Python -m alembic upgrade head
    } finally {
        Pop-Location
    }
} else {
    $bootstrapModule = Join-Path $Root "backend\app\core\generated_db_bootstrap.py"
    if (Test-Path $bootstrapModule) {
        Write-Host "Alembic is missing; running generated SQLAlchemy bootstrap."
        Push-Location (Join-Path $Root "backend")
        try {
            & $Python -m app.core.generated_db_bootstrap
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning "backend\alembic.ini and generated_db_bootstrap.py are missing; no migration command was run."
    }
}
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "migrate.ps1")

@'
param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [string]$HostAddress = "127.0.0.1",
    [int]$BackendPort = 8000,
    [switch]$WithFrontend,
    [switch]$Background
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"
$LogPath = Join-Path $Root "logs"
New-Item -ItemType Directory -Force $RuntimePath | Out-Null
New-Item -ItemType Directory -Force $LogPath | Out-Null

function Test-RunningPid([string]$PidPath) {
    if (-not (Test-Path $PidPath)) {
        return $false
    }

    $rawPid = (Get-Content -Raw -Encoding UTF8 $PidPath).Trim()
    if ([string]::IsNullOrWhiteSpace($rawPid)) {
        return $false
    }

    try {
        $process = Get-Process -Id ([int]$rawPid) -ErrorAction Stop
        return -not $process.HasExited
    } catch {
        return $false
    }
}

& (Join-Path $PSScriptRoot "check-prerequisites.ps1") -Root $Root | Out-Host

$envPath = Join-Path $Root ".env"
$envExamplePath = Join-Path $Root ".env.example"
if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created .env from .env.example"
}

if ($Background) {
    $backendPidPath = Join-Path $RuntimePath "backend.pid"
    if (Test-RunningPid $backendPidPath) {
        throw "Backend is already running. Use scripts\status.ps1 or scripts\restart.ps1."
    }

    $backendOut = Join-Path $LogPath "backend.out.log"
    $backendErr = Join-Path $LogPath "backend.err.log"
    $backendProcess = Start-Process $Python -ArgumentList @(
        "-m", "uvicorn", "app.main:app",
        "--host", $HostAddress,
        "--port", [string]$BackendPort
    ) -WorkingDirectory (Join-Path $Root "backend") `
      -WindowStyle Hidden `
      -RedirectStandardOutput $backendOut `
      -RedirectStandardError $backendErr `
      -PassThru
    [string]$backendProcess.Id | Set-Content -Encoding UTF8 $backendPidPath

    $frontendPid = $null
    if ($WithFrontend) {
        $frontendPackage = Join-Path $Root "frontend\package.json"
        if (-not (Test-Path $frontendPackage)) {
            throw "Cannot start frontend because frontend\package.json is missing."
        }

        $frontendPidPath = Join-Path $RuntimePath "frontend.pid"
        if (Test-RunningPid $frontendPidPath) {
            throw "Frontend is already running. Use scripts\status.ps1 or scripts\restart.ps1."
        }

        $frontendOut = Join-Path $LogPath "frontend.out.log"
        $frontendErr = Join-Path $LogPath "frontend.err.log"
        $frontendProcess = Start-Process $Npm -ArgumentList @("run", "dev") `
          -WorkingDirectory (Join-Path $Root "frontend") `
          -WindowStyle Hidden `
          -RedirectStandardOutput $frontendOut `
          -RedirectStandardError $frontendErr `
          -PassThru
        [string]$frontendProcess.Id | Set-Content -Encoding UTF8 $frontendPidPath
        $frontendPid = $frontendProcess.Id
    }

    [ordered]@{
        backend = [ordered]@{
            pid = $backendProcess.Id
            url = "http://$HostAddress`:$BackendPort"
            stdout = "logs\backend.out.log"
            stderr = "logs\backend.err.log"
        }
        frontend = [ordered]@{
            requested = [bool]$WithFrontend
            pid = $frontendPid
            stdout = if ($WithFrontend) { "logs\frontend.out.log" } else { $null }
            stderr = if ($WithFrontend) { "logs\frontend.err.log" } else { $null }
        }
    } | ConvertTo-Json -Depth 10

    Write-Host "Background processes started. Use scripts\status.ps1 to inspect them."
    return
}

if ($WithFrontend) {
    $frontendPackage = Join-Path $Root "frontend\package.json"
    if (-not (Test-Path $frontendPackage)) {
        throw "Cannot start frontend because frontend\package.json is missing."
    }

    Write-Host "Starting frontend dev server in a new PowerShell process."
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", "Set-Location '$Root\frontend'; $Npm run dev"
    ) -WindowStyle Hidden | Out-Null
}

Write-Host "Starting backend on http://$HostAddress`:$BackendPort"
Push-Location (Join-Path $Root "backend")
try {
    & $Python -m uvicorn app.main:app --host $HostAddress --port $BackendPort
} finally {
    Pop-Location
}
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "start.ps1")

@'
param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"
$LogPath = Join-Path $Root "logs"

function Get-ServiceStatus([string]$Name) {
    $pidPath = Join-Path $RuntimePath "$Name.pid"
    $pidValue = $null
    $running = $false

    if (Test-Path $pidPath) {
        $rawPid = (Get-Content -Raw -Encoding UTF8 $pidPath).Trim()
        if (-not [string]::IsNullOrWhiteSpace($rawPid)) {
            $pidValue = [int]$rawPid
            try {
                Get-Process -Id $pidValue -ErrorAction Stop | Out-Null
                $running = $true
            } catch {
                $running = $false
            }
        }
    }

    return [ordered]@{
        pid = $pidValue
        running = $running
        pidFile = "runtime\$Name.pid"
        stdout = "logs\$Name.out.log"
        stderr = "logs\$Name.err.log"
        stdoutExists = Test-Path (Join-Path $LogPath "$Name.out.log")
        stderrExists = Test-Path (Join-Path $LogPath "$Name.err.log")
    }
}

[ordered]@{
    root = $Root
    backend = Get-ServiceStatus "backend"
    frontend = Get-ServiceStatus "frontend"
} | ConvertTo-Json -Depth 10
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "status.ps1")

@'
param(
    [switch]$FrontendOnly,
    [switch]$BackendOnly
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$RuntimePath = Join-Path $Root "runtime"

function Stop-ServiceByPidFile([string]$Name) {
    $pidPath = Join-Path $RuntimePath "$Name.pid"
    $result = [ordered]@{
        name = $Name
        pid = $null
        stopped = $false
        wasRunning = $false
    }

    if (-not (Test-Path $pidPath)) {
        return $result
    }

    $rawPid = (Get-Content -Raw -Encoding UTF8 $pidPath).Trim()
    if (-not [string]::IsNullOrWhiteSpace($rawPid)) {
        $result.pid = [int]$rawPid
        try {
            $process = Get-Process -Id $result.pid -ErrorAction Stop
            $result.wasRunning = $true
            Stop-Process -Id $process.Id -Force
            $result.stopped = $true
        } catch {
            $result.wasRunning = $false
        }
    }

    Remove-Item -LiteralPath $pidPath -Force
    return $result
}

$results = New-Object System.Collections.Generic.List[object]
if (-not $FrontendOnly) {
    $results.Add((Stop-ServiceByPidFile "backend"))
}
if (-not $BackendOnly) {
    $results.Add((Stop-ServiceByPidFile "frontend"))
}

[ordered]@{
    root = $Root
    results = $results.ToArray()
} | ConvertTo-Json -Depth 10
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "stop.ps1")

@'
param(
    [string]$Python = "python",
    [string]$Npm = "npm",
    [string]$HostAddress = "127.0.0.1",
    [int]$BackendPort = 8000,
    [switch]$WithFrontend
)

$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "stop.ps1") | Out-Host
& (Join-Path $PSScriptRoot "start.ps1") `
    -Python $Python `
    -Npm $Npm `
    -HostAddress $HostAddress `
    -BackendPort $BackendPort `
    -WithFrontend:$WithFrontend `
    -Background
'@ | Set-Content -Encoding UTF8 (Join-Path $scriptsPath "restart.ps1")

@"
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/form_system
AUTH_MODE=api_key
MULTI_TENANT_ENABLED=true
AUDIT_EVENTS_ENABLED=false
USE_GENERIC_SCHEMA=false
PDF_SERVER_URL=
ENTITLEMENT_MODE=local
"@ | Set-Content -Encoding UTF8 (Join-Path $outputPath ".env.example")

$manifest = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    sourceRecipe = $plan.recipe
    resolvedKitOrder = $plan.resolvedKitOrder
    database = $plan.database
    scripts = @(
        "scripts\check-prerequisites.ps1",
        "scripts\check-db.ps1",
        "scripts\install.ps1",
        "scripts\migrate.ps1",
        "scripts\smoke-start.ps1",
        "scripts\status.ps1",
        "scripts\stop.ps1",
        "scripts\restart.ps1",
        "scripts\start.ps1"
    )
    dependencyManifest = "dependency-manifest.json"
    dependencyPlan = "dependency-plan.json"
    dbBootstrapPlan = "db-bootstrap-plan.json"
    status = "runnable-envelope"
}
$manifest | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $outputPath "package-manifest.json")

@"
# Generated System

This folder is generated by ``tools/assemble-system.ps1``.

## First Run

```powershell
.\scripts\check-prerequisites.ps1
.\scripts\check-db.ps1
.\scripts\install.ps1
.\scripts\migrate.ps1
.\scripts\smoke-start.ps1
.\scripts\start.ps1 -Background
```

To also start the frontend dev server:

```powershell
.\scripts\start.ps1 -WithFrontend -Background
```

To inspect or stop background processes:

```powershell
.\scripts\status.ps1
.\scripts\stop.ps1
.\scripts\restart.ps1
```

## Runtime Contract

The package is a runnable envelope: selected source files, generated registries,
environment template, dependency manifest, and scripts are present.

Dependency files are generated from the selected backend and frontend imports.
Review ``dependency-plan.json`` before production deployment and pin exact
versions when the target runtime is decided.

Database bootstrap files are generated from ``assembly\db-plan``. Run
``.\scripts\check-db.ps1`` for structural validation, or
``.\scripts\check-db.ps1 -Connect`` when a real database is available.

Run ``.\scripts\smoke-start.ps1`` before startup to compile the backend and
verify that start scripts are wired. After dependencies are installed, add
``-ImportApp``. With a real database available, add ``-StartBackend`` to verify
the `/healthz` endpoint.

Background processes write pid files to ``runtime`` and logs to ``logs``.
"@ | Set-Content -Encoding UTF8 (Join-Path $outputPath "README.md")

if ($CreateZip) {
    $zipPath = "$outputPath.zip"
    if (Test-Path $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $outputPath "*") -DestinationPath $zipPath -Force
    Write-Host "Generated system zip written to $zipPath"
}

Write-Host "Generated system written to $outputPath"
