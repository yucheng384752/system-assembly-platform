param(
    [string]$DeployDir = "dist\client-deploy-gui-selected-form-system",
    [string]$OutputDir = "dist\offline-bundle"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$DeployPath = Join-Path $RepoRoot $DeployDir
$OutputPath = Join-Path $RepoRoot $OutputDir

Write-Host "=== Form System offline bundle ===" -ForegroundColor Cyan
Write-Host "deploy: $DeployPath"
Write-Host "output: $OutputPath"
Write-Host ""

if (-not (Test-Path $DeployPath)) {
    throw "Deploy directory not found: $DeployPath"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required to create the offline image bundle."
}

New-Item -ItemType Directory -Force -Path (Join-Path $OutputPath "docker-images") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $OutputPath "system") | Out-Null

$Images = @(
    "postgres:15-alpine",
    "nginx:alpine",
    "python:3.11-slim",
    "node:20-slim"
)

Write-Host ">> Pulling Docker images..." -ForegroundColor Yellow
foreach ($image in $Images) {
    Write-Host "   pulling $image"
    docker pull $image
    if ($LASTEXITCODE -ne 0) {
        throw "docker pull failed: $image"
    }
}

$TarPath = Join-Path $OutputPath "docker-images\images.tar"
Write-Host "   saving -> $TarPath"
docker save @Images -o $TarPath
if ($LASTEXITCODE -ne 0) {
    throw "docker save failed."
}
Write-Host ("   {0:N0} MB  docker-images\images.tar" -f ((Get-Item $TarPath).Length / 1MB))

Write-Host ""
Write-Host ">> Copying deploy package..." -ForegroundColor Yellow
Copy-Item -Path (Join-Path $DeployPath "*") -Destination (Join-Path $OutputPath "system") -Recurse -Force
"offline" | Set-Content (Join-Path $OutputPath "system\.offline-mode") -Encoding UTF8

$LoadScript = @'
$Here = Split-Path $MyInvocation.MyCommand.Path
docker load -i "$Here\docker-images\images.tar"
Write-Host "Loaded Docker images:"
docker images --format "  {{.Repository}}:{{.Tag}}  ({{.Size}})"
'@
$LoadScript | Set-Content (Join-Path $OutputPath "load-docker-images.ps1") -Encoding UTF8

Write-Host ""
Write-Host "=== Offline bundle complete ===" -ForegroundColor Green
Write-Host "output: $OutputPath"
$TotalMB = [math]::Round((Get-ChildItem $OutputPath -Recurse | Measure-Object Length -Sum).Sum / 1MB, 0)
Write-Host "size  : ${TotalMB} MB"
Write-Host ""
Write-Host "Client steps:"
Write-Host "  1. Copy this folder to the offline machine."
Write-Host "  2. Run: .\load-docker-images.ps1"
Write-Host "  3. Run the deploy script from system\."
