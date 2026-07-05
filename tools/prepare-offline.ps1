#Requires -Version 5.1
<#
.SYNOPSIS
    離線部署套件準備工具 — Form System Kit Composer

.DESCRIPTION
    在打包「離線版」客戶部署套件之前，預先下載所有需要網路連線的依賴：
      - Python pip wheels (system/backend/wheels/)
    執行此腳本後，再至 Kit Composer GUI 下載「離線版」.zip。

    install-wizard.py 在離線模式下會偵測 system/backend/wheels/ 目錄，
    並使用 pip install --find-links wheels/ --no-index 取代聯網安裝。

.NOTES
    前置條件：
      1. Python 3.10+ 已安裝
      2. system/ 目錄已存在（執行過 tools/assemble-system.ps1）

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\prepare-offline.ps1
    powershell -ExecutionPolicy Bypass -File tools\prepare-offline.ps1 -SystemDir "dist\generated-system"
#>
param(
    [string]$SystemDir = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$RepoRoot  = Split-Path $ScriptDir -Parent

function Write-OK   ([string]$msg) { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Write-Info ([string]$msg) { Write-Host "  [INFO] $msg" -ForegroundColor Yellow }
function Write-Warn ([string]$msg) { Write-Host "  [WARN] $msg" -ForegroundColor DarkYellow }
function Die        ([string]$msg) { Write-Host "  [ERR]  $msg" -ForegroundColor Red; exit 1 }

Write-Host "======================================================"
Write-Host "  Form System Kit Composer — 離線套件準備"
Write-Host "======================================================"

# ── 1. 找 system 目錄 ────────────────────────────────────────────────────────
if (-not $SystemDir) {
    $candidates = @(
        (Join-Path $RepoRoot "dist\client-deploy-gui-selected-form-system\system"),
        (Join-Path $RepoRoot "dist\generated-system"),
        (Join-Path $RepoRoot "generated\mvp-import-flow\form-analysis-server")
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c "backend\requirements.txt")) {
            $SystemDir = $c
            break
        }
    }
}

if (-not $SystemDir -or -not (Test-Path (Join-Path $SystemDir "backend\requirements.txt"))) {
    Die "找不到 system 目錄（需包含 backend/requirements.txt）。`n請先執行 tools/assemble-system.ps1，或指定 -SystemDir 參數。"
}
Write-OK "system 目錄: $SystemDir"

$BackendDir = Join-Path $SystemDir "backend"
$ReqFile    = Join-Path $BackendDir "requirements.txt"
$WheelsDir  = Join-Path $BackendDir "wheels"

# ── 2. 建立 wheels 目錄 ──────────────────────────────────────────────────────
if (-not (Test-Path $WheelsDir)) {
    New-Item -ItemType Directory -Force $WheelsDir | Out-Null
    Write-OK "建立 wheels 目錄: $WheelsDir"
} else {
    Write-Info "wheels 目錄已存在，將更新: $WheelsDir"
}

# ── 3. 下載 pip wheels ────────────────────────────────────────────────────────
Write-Info "開始下載 pip wheels（需要網路）..."
Write-Info "requirements.txt: $ReqFile"

$pip = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $pip) { Die "找不到 python，請確認 Python 3.10+ 已安裝並在 PATH 中" }

Write-Info "使用 Python: $pip"
Write-Info "下載至: $WheelsDir"
Write-Host ""

$result = & python -m pip download `
    --dest "$WheelsDir" `
    --platform linux_x86_64 `
    --python-version "310" `
    --only-binary=:all: `
    -r "$ReqFile" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Warn "部分套件無法取得 linux_x86_64 預編譯版本，嘗試下載 any 平台..."
    $result2 = & python -m pip download `
        --dest "$WheelsDir" `
        -r "$ReqFile" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Die "pip download 失敗。請確認網路連線，或手動執行：`n  pip download --dest $WheelsDir -r $ReqFile"
    }
}

$wheelCount = (Get-ChildItem $WheelsDir -Filter "*.whl" -ErrorAction SilentlyContinue).Count
$tarCount   = (Get-ChildItem $WheelsDir -Filter "*.tar.gz" -ErrorAction SilentlyContinue).Count
Write-OK "wheels 下載完成：$wheelCount .whl + $tarCount .tar.gz"

# ── 4. 摘要 ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "======================================================"
Write-Host "  離線套件準備完成！" -ForegroundColor Green
Write-Host "======================================================"
Write-Host "  wheels 目錄   : $WheelsDir"
Write-Host "  套件數量      : $($wheelCount + $tarCount) 個"
Write-Host ""
Write-Host "  下一步："
Write-Host "    1. 至 Kit Composer GUI (http://localhost:4174)"
Write-Host "    2. Step 3 選擇「離線版」"
Write-Host "    3. 點擊「下載 .zip」"
Write-Host "    4. 將 ZIP 交給部署人員（無需網路即可安裝）"
Write-Host ""
Write-Host "  install-wizard.py 在離線模式下會自動使用："
Write-Host "    pip install --find-links wheels/ --no-index -r requirements.txt"
Write-Host "======================================================"
