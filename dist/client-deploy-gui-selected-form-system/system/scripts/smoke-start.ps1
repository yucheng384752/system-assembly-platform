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
