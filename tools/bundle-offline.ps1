#Requires -Version 5.1
<#
.SYNOPSIS
    在有網路的機器上執行，產生 Windows 離線安裝包。

.DESCRIPTION
    拉取所有 Docker 映像並儲存為 .tar 檔，連同部署包一起打包，
    之後可以用 USB 帶入無網路的 Windows 目標機器安裝。

.PARAMETER DeployDir
    部署包目錄（相對於 repo 根目錄）。

.PARAMETER OutputDir
    輸出目錄（相對於 repo 根目錄）。

.EXAMPLE
    .\tools\bundle-offline.ps1
    .\tools\bundle-offline.ps1 -DeployDir dist\client-deploy-gui-selected-form-system -OutputDir dist\offline-bundle
#>
param(
    [string]$DeployDir  = "dist\client-deploy-gui-selected-form-system",
    [string]$OutputDir  = "dist\offline-bundle"
)

$ErrorActionPreference = "Stop"

$RepoRoot   = (Resolve-Path "$PSScriptRoot\..").Path
$DeployPath = Join-Path $RepoRoot $DeployDir
$OutputPath = Join-Path $RepoRoot $OutputDir

Write-Host "=== Form System 離線包打包工具 ===" -ForegroundColor Cyan
Write-Host "來源: $DeployPath"
Write-Host "輸出: $OutputPath"
Write-Host ""

# ── 1. 確認 Docker 可用 ────────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "需要 Docker Desktop。請先在有網路的機器安裝後再執行。"
    exit 1
}

New-Item -ItemType Directory -Force -Path "$OutputPath\docker-images" | Out-Null
New-Item -ItemType Directory -Force -Path "$OutputPath\system"        | Out-Null

# ── 2. 拉取並儲存映像 ──────────────────────────────────────────────────────
$Images = @(
    "postgres:15-alpine",
    "nginx:alpine",
    "python:3.11-slim"
)

Write-Host ">> 拉取 Docker 映像..." -ForegroundColor Yellow
foreach ($img in $Images) {
    Write-Host "   pulling $img"
    docker pull $img
}

$TarPath = "$OutputPath\docker-images\images.tar"
Write-Host "   saving -> $TarPath"
docker save @Images -o $TarPath
Write-Host ("   {0:N0} MB  docker-images\images.tar" -f ((Get-Item $TarPath).Length / 1MB))

# ── 3. 複製部署包 ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host ">> 複製部署包..." -ForegroundColor Yellow
Copy-Item -Path "$DeployPath\*" -Destination "$OutputPath\system\" -Recurse -Force

# ── 4. 寫入 offline 旗標 ───────────────────────────────────────────────────
"offline" | Set-Content "$OutputPath\system\.offline-mode" -Encoding UTF8

# ── 5. 產生 Docker 載入腳本 ───────────────────────────────────────────────
$LoadScript = @"
# load-docker-images.ps1 — 在目標機器（無網路）執行
# 前提：Docker Desktop 已安裝（需先用 winget 或安裝程式離線安裝）
#
# Docker Desktop 離線安裝：
#   從 https://docs.docker.com/desktop/install/windows-install/ 下載
#   Docker Desktop Installer.exe，複製到 USB 一起帶入。

`$Here = Split-Path `$MyInvocation.MyCommand.Path
docker load -i "`$Here\docker-images\images.tar"
Write-Host "映像載入完成:"
docker images --format "  {{.Repository}}:{{.Tag}}  ({{.Size}})"
"@
$LoadScript | Set-Content "$OutputPath\load-docker-images.ps1" -Encoding UTF8

# ── 6. 顯示摘要 ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== 打包完成 ===" -ForegroundColor Green
Write-Host "輸出目錄: $OutputPath"
$TotalMB = [math]::Round((Get-ChildItem $OutputPath -Recurse | Measure-Object Length -Sum).Sum / 1MB, 0)
Write-Host "總大小: ${TotalMB} MB"
Write-Host ""
Write-Host "目標機器安裝步驟："
Write-Host "  1. 把 $OutputDir 整個資料夾複製到 USB"
Write-Host "  2. 在目標機器執行: .\load-docker-images.ps1"
Write-Host "  3. 執行: python3 system\install-wizard.py"
