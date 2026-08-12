#Requires -Version 5.1
<#
.SYNOPSIS
    Windows 機器簽章金鑰初始化 — Form System Kit Composer (HiBA-AB)
    對應 Linux 版：01_tpm_full_setup.sh

.DESCRIPTION
    建立（或重用）持久化 RSA-2048 機器簽章金鑰：
      - 硬體 TPM 2.0 就緒 → Microsoft Platform Crypto Provider（TPM 綁定）
      - 無硬體 TPM         → Microsoft Software Key Storage Provider（軟體金鑰）
    金鑰以 MachineKey 範圍儲存，重開機後保留。
    冪等：金鑰已存在則直接匯出公鑰，不重建。

.OUTPUTS
    machine-pubkey.pem       — RSA-2048 SubjectPublicKeyInfo PEM（上傳至 Kit Composer）
    machine-fingerprint.txt  — SHA-256 of DER（同 Linux ek_fingerprint.txt）

.NOTES
    需要以「系統管理員」身分執行（MachineKey 需要管理員權限）。
    用法：  .\01_tpm_setup_windows.ps1
            .\01_tpm_setup_windows.ps1 -OutputDir C:\path\to\output
#>
param(
    [string]$OutputDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

$KEY_NAME    = "HiBA-Machine-Signing-Key"
$PUBKEY_FILE = Join-Path $OutputDir "machine-pubkey.pem"
$FP_FILE     = Join-Path $OutputDir "machine-fingerprint.txt"

function Write-OK   ([string]$msg) { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Write-Info ([string]$msg) { Write-Host "  [INFO] $msg" -ForegroundColor Yellow }
function Write-Skip ([string]$msg) { Write-Host "  [SKIP] $msg (已存在，冪等)" -ForegroundColor Cyan }
function Write-Warn ([string]$msg) { Write-Host "  [WARN] $msg" -ForegroundColor DarkYellow }
function Write-Fail ([string]$msg) { Write-Host "  [ERR]  $msg" -ForegroundColor Red }
function Die        ([string]$msg) { Write-Fail $msg; exit 1 }

# ── DER 編碼工具（相容 .NET Framework 4.x / PowerShell 5.1） ────────────────

function Private:Encode-DerLen([int]$n) {
    if ($n -lt 0x80) { return [byte[]]@([byte]$n) }
    if ($n -lt 0x100) { return [byte[]]@([byte]0x81, [byte]$n) }
    return [byte[]]@([byte]0x82, [byte](($n -shr 8) -band 0xFF), [byte]($n -band 0xFF))
}

function Private:Encode-DerTLV([byte]$tag, [byte[]]$value) {
    $ms = New-Object System.IO.MemoryStream
    $ms.WriteByte($tag)
    $lenBytes = Encode-DerLen $value.Length
    $ms.Write($lenBytes, 0, $lenBytes.Length)
    $ms.Write($value, 0, $value.Length)
    return [byte[]]$ms.ToArray()
}

function Private:Encode-DerInteger([byte[]]$bytes) {
    # strip leading 0x00 except one, prepend 0x00 if high bit set (positive integer sign)
    $i = 0
    while ($i -lt ($bytes.Length - 1) -and $bytes[$i] -eq 0) { $i++ }
    $trimmed = $bytes[$i..($bytes.Length - 1)]
    if ($trimmed[0] -band 0x80) {
        $withSign = New-Object System.Collections.Generic.List[byte]
        $withSign.Add([byte]0x00)
        $withSign.AddRange([byte[]]$trimmed)
        $trimmed = $withSign.ToArray()
    }
    return Encode-DerTLV 0x02 $trimmed
}

function Build-SpkiDer([System.Security.Cryptography.RSA]$rsa) {
    <#
    SubjectPublicKeyInfo ::= SEQUENCE {
      algorithm   AlgorithmIdentifier,   -- rsaEncryption OID + NULL
      subjectPublicKey  BIT STRING { RSAPublicKey }
    }
    RSAPublicKey ::= SEQUENCE { modulus INTEGER, publicExponent INTEGER }
    #>
    $p = $rsa.ExportParameters($false)

    $modInt  = Encode-DerInteger $p.Modulus
    $expInt  = Encode-DerInteger $p.Exponent
    $rsaBody = Encode-DerTLV 0x30 ([byte[]]($modInt + $expInt))

    # BIT STRING: 0x00 (no unused bits) + RSAPublicKey
    $bitStrContent = [byte[]]@([byte]0x00) + $rsaBody
    $bitStr = Encode-DerTLV 0x03 $bitStrContent

    # AlgorithmIdentifier: OID rsaEncryption (1.2.840.113549.1.1.1) + NULL
    $algId = [byte[]]@(
        0x30, 0x0D,                                   # SEQUENCE, 13 bytes
        0x06, 0x09,                                   # OID, 9 bytes
        0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x01,  # 1.2.840.113549.1.1.1
        0x05, 0x00                                    # NULL
    )

    return [byte[]](Encode-DerTLV 0x30 ([byte[]]($algId + $bitStr)))
}

# ── 主程式 ──────────────────────────────────────────────────────────────────

Write-Host "======================================================"
Write-Host "  Form System Kit Composer — Windows 機器金鑰初始化"
Write-Host "======================================================"

# ── STAGE 0: 確認管理員權限 ─────────────────────────────────────────────────
Write-Info "STAGE 0: 確認執行環境"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
    Die "需要以管理員身分執行。請在「系統管理員」PowerShell 視窗中重試：`n  Right-click PowerShell → 以系統管理員身分執行"
}
Write-OK "管理員權限確認"

# ── STAGE 1: 偵測 TPM ──────────────────────────────────────────────────────
Write-Info "STAGE 1: 偵測硬體 TPM"

$hasHwTpm = $false
try {
    $tpmStatus = Get-Tpm -ErrorAction Stop
    $hasHwTpm  = $tpmStatus.TpmPresent -and $tpmStatus.TpmReady
    if ($hasHwTpm) {
        Write-OK "硬體 TPM 2.0 就緒 (Spec: $($tpmStatus.SpecVersion), Enabled: $($tpmStatus.TpmEnabled))"
    } else {
        Write-Warn "TPM 存在但未就緒 (Present=$($tpmStatus.TpmPresent), Ready=$($tpmStatus.TpmReady))"
    }
} catch {
    Write-Warn "Get-Tpm 失敗或無 TPM: $_"
}

$provider = if ($hasHwTpm) {
    "Microsoft Platform Crypto Provider"
} else {
    Write-Info "無硬體 TPM，使用軟體金鑰存放 (Microsoft Software Key Storage Provider)"
    Write-Info "注意: 軟體金鑰無 TPM 硬體保護，僅適合開發 / 測試環境"
    "Microsoft Software Key Storage Provider"
}
Write-Info "選用 Provider: $provider"

# ── STAGE 2: 建立或重用機器簽章金鑰 ────────────────────────────────────────
Write-Info "STAGE 2: 建立/重用 RSA-2048 機器簽章金鑰"

Add-Type -AssemblyName System.Security

$cngProvider = New-Object System.Security.Cryptography.CngProvider($provider)
$keyOpenOpts  = [System.Security.Cryptography.CngKeyOpenOptions]::MachineKey

$cngKey = $null
$isNew  = $false

try {
    $cngKey = [System.Security.Cryptography.CngKey]::Open($KEY_NAME, $cngProvider, $keyOpenOpts)
    Write-Skip "金鑰 '$KEY_NAME' 已存在於 $provider"
} catch {
    Write-Info "建立新金鑰 '$KEY_NAME'..."
    $kcp = New-Object System.Security.Cryptography.CngKeyCreationParameters
    $kcp.Provider         = $cngProvider
    $kcp.ExportPolicy     = [System.Security.Cryptography.CngExportPolicies]::None
    $kcp.KeyUsage         = [System.Security.Cryptography.CngKeyUsages]::Signing
    $kcp.KeyCreationOptions = [System.Security.Cryptography.CngKeyCreationOptions]::MachineKey

    # 設定金鑰長度 2048 bits
    $szBytes = [System.BitConverter]::GetBytes([int32]2048)
    $lenProp = New-Object System.Security.Cryptography.CngProperty(
        "Length", $szBytes, [System.Security.Cryptography.CngPropertyOptions]::None
    )
    $kcp.Parameters.Add($lenProp)

    try {
        $cngKey = [System.Security.Cryptography.CngKey]::Create(
            [System.Security.Cryptography.CngAlgorithm]::Rsa, $KEY_NAME, $kcp
        )
        $isNew = $true
        Write-OK "RSA-2048 機器金鑰建立完成（MachineKey 範圍，重開機保留）"
    } catch {
        Die "金鑰建立失敗: $_`n請確認以管理員身分執行，且 Provider 支援此操作。"
    }
}

# ── STAGE 3: 匯出公鑰為 PEM ────────────────────────────────────────────────
Write-Info "STAGE 3: 匯出公鑰 → machine-pubkey.pem"

try {
    $rsaObj  = New-Object System.Security.Cryptography.RSACng($cngKey)
    $spkiDer = Build-SpkiDer $rsaObj
} catch {
    Die "公鑰匯出失敗: $_"
}

$b64Lines = @()
$b64      = [System.Convert]::ToBase64String($spkiDer)
for ($i = 0; $i -lt $b64.Length; $i += 64) {
    $b64Lines += $b64.Substring($i, [Math]::Min(64, $b64.Length - $i))
}
$pem = "-----BEGIN PUBLIC KEY-----`r`n" + ($b64Lines -join "`r`n") + "`r`n-----END PUBLIC KEY-----`r`n"
[System.IO.File]::WriteAllText($PUBKEY_FILE, $pem, [System.Text.Encoding]::ASCII)
Write-OK "machine-pubkey.pem 儲存至: $PUBKEY_FILE"

# ── STAGE 4: 計算 EK Fingerprint ────────────────────────────────────────────
Write-Info "STAGE 4: 計算 EK Fingerprint (SHA-256 of DER)"

$sha256  = [System.Security.Cryptography.SHA256]::Create()
$fpBytes = $sha256.ComputeHash($spkiDer)
$fp      = ($fpBytes | ForEach-Object { $_.ToString("x2") }) -join ""
[System.IO.File]::WriteAllText($FP_FILE, $fp, [System.Text.Encoding]::ASCII)
Write-OK "EK Fingerprint: $fp"

# ── STAGE 5: 簽章測試（驗證金鑰可用性）────────────────────────────────────
Write-Info "STAGE 5: 簽章測試"

try {
    $testData = [System.Text.Encoding]::UTF8.GetBytes("hiba-test")
    $rsaSign  = New-Object System.Security.Cryptography.RSACng($cngKey)
    $sig      = $rsaSign.SignData(
        $testData,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
    )
    $ok = $rsaSign.VerifyData(
        $testData, $sig,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
    )
    if ($ok) { Write-OK "簽章 + 驗簽通過（RSA-SHA256-PKCS1）" }
    else      { Write-Warn "驗簽回傳 false（非致命）" }
} catch {
    Write-Warn "簽章測試失敗（非致命）: $_"
}

# ── 完成摘要 ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "======================================================"
Write-Host "  機器金鑰初始化完成！" -ForegroundColor Green
Write-Host "======================================================"
Write-Host "  Provider       : $provider"
Write-Host "  Key Name       : $KEY_NAME"
Write-Host "  Key Scope      : MachineKey（開機保留，不可匯出私鑰）"
Write-Host "  Public Key     : $PUBKEY_FILE"
Write-Host "  EK Fingerprint : $fp"
Write-Host ""
Write-Host "  下一步："
Write-Host "    將 machine-pubkey.pem 上傳至 Form System Kit Composer 平台"
Write-Host "    以取得機器綁定授權"
Write-Host ""
if (-not $hasHwTpm) {
    Write-Host "  注意: 軟體金鑰（非 TPM 硬體綁定）" -ForegroundColor DarkYellow
    Write-Host "        金鑰受 Windows DPAPI 機器密鑰保護" -ForegroundColor DarkYellow
    Write-Host "        建議在正式伺服器上使用具備 TPM 2.0 的硬體" -ForegroundColor DarkYellow
}
Write-Host "======================================================"
Write-Host ""
Write-Host "  若需重新匯出公鑰（金鑰已存在時），再次執行此腳本即可。"
Write-Host "  勿刪除金鑰（$KEY_NAME），否則機器指紋將改變，授權失效。"
Write-Host ""
