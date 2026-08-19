#!/usr/bin/env python3
"""
TPM + License 診斷工具
在部署機上執行：python3 diagnose-tpm-license.py
輸出貼給開發者分析錯誤來源。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_TPM_HANDLE = "0x81000001"
_TPM_PEM_PATH = Path("/opt/hiba/tpm/signing_public.pem")

SEP = "=" * 60


def hdr(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


# ── 1. 環境 ───────────────────────────────────────────────────────────────────
hdr("1. 環境")
info(f"Python  : {sys.version.split()[0]}")
info(f"OS      : {platform.system()} {platform.release()}")
info(f"CWD     : {os.getcwd()}")
info(f"USER    : {os.environ.get('USER', os.environ.get('USERNAME', '?'))}")
info(f"TCTI    : {os.environ.get('TPM2TOOLS_TCTI', '(not set)')}")

# ── 2. TPM 工具 ───────────────────────────────────────────────────────────────
hdr("2. TPM 工具可用性")
for cmd in ["tpm2_sign", "tpm2_readpublic", "tpm2_getcap", "swtpm"]:
    path = shutil.which(cmd)
    if path:
        ok(f"{cmd:20s} → {path}")
    else:
        warn(f"{cmd:20s} → 找不到（未安裝）")

# ── 3. swtpm 狀態 ─────────────────────────────────────────────────────────────
hdr("3. swtpm 持久化狀態")
swtpm_marker = Path("/opt/hiba/tpm/swtpm-state/.initialized")
if swtpm_marker.exists():
    ok(f"swtpm 已初始化：{swtpm_marker}")
    # 確認 swtpm 行程是否在跑
    try:
        r = subprocess.run(["pgrep", "-a", "swtpm"], capture_output=True, text=True, timeout=3)
        if r.stdout.strip():
            ok(f"swtpm 行程：{r.stdout.strip()[:120]}")
        else:
            warn("swtpm 行程未偵測到（可能需要 systemd socket 啟動）")
    except Exception as e:
        warn(f"pgrep swtpm 失敗：{e}")
else:
    warn(f"swtpm 未初始化（{swtpm_marker} 不存在）")
    info("若使用硬體 TPM (/dev/tpmrm0) 則此項正常")

for dev in ["/dev/tpmrm0", "/dev/tpm0"]:
    if Path(dev).exists():
        ok(f"硬體 TPM 裝置：{dev}")

# ── 4. TPM 公鑰檔 ─────────────────────────────────────────────────────────────
hdr(f"4. /opt/hiba/tpm/signing_public.pem")
local_pem: str | None = None
if _TPM_PEM_PATH.exists():
    try:
        local_pem = _TPM_PEM_PATH.read_text("utf-8").strip()
        lines = local_pem.splitlines()
        ok(f"檔案存在，{len(lines)} 行")
        b64 = "".join(l for l in lines if not l.startswith("-----"))
        info(f"公鑰縮略：{b64[:20]}…{b64[-16:]}")
        fp = hashlib.sha256(local_pem.encode()).hexdigest()
        info(f"SHA256(pem_text): {fp}")
    except Exception as e:
        fail(f"讀取失敗：{e}")
else:
    fail(f"檔案不存在：{_TPM_PEM_PATH}")
    info("請執行 01_tpm_full_setup.sh 或 get-machine-pubkey.sh")

# ── 5. TPM handle 0x81000001 ──────────────────────────────────────────────────
hdr(f"5. TPM handle {_TPM_HANDLE}")
handle_pem: str | None = None
if shutil.which("tpm2_readpublic"):
    env = dict(os.environ)
    if not env.get("TPM2TOOLS_TCTI") and swtpm_marker.exists():
        env["TPM2TOOLS_TCTI"] = "swtpm:host=127.0.0.1,port=2321"
        info(f"自動設定 TCTI=swtpm:host=127.0.0.1,port=2321")

    with tempfile.TemporaryDirectory() as d:
        pem_out = Path(d) / "handle.pem"
        r = subprocess.run(
            ["tpm2_readpublic", "--object-context", _TPM_HANDLE,
             "--output", str(pem_out), "--format", "pem"],
            capture_output=True, text=True, timeout=10, env=env,
        )
        if r.returncode == 0 and pem_out.exists():
            handle_pem = pem_out.read_text("utf-8").strip()
            b64 = "".join(l for l in handle_pem.splitlines() if not l.startswith("-----"))
            ok(f"handle 存在，公鑰縮略：{b64[:20]}…{b64[-16:]}")
            fp = hashlib.sha256(handle_pem.encode()).hexdigest()
            info(f"SHA256(pem_text): {fp}")

            if local_pem and handle_pem:
                def _norm(p):
                    return "\n".join(l.strip() for l in p.strip().splitlines() if l.strip())
                if _norm(local_pem) == _norm(handle_pem):
                    ok("signing_public.pem 與 handle 公鑰一致 ✓")
                else:
                    fail("signing_public.pem 與 handle 公鑰不一致！PEM 檔可能過期或指向不同 handle")
        else:
            fail(f"tpm2_readpublic 失敗 (rc={r.returncode})")
            if r.stderr:
                info(f"stderr: {r.stderr.strip()[:300]}")
else:
    warn("tpm2_readpublic 不可用，跳過 handle 檢查")

# ── 6. TPM 簽名測試 ───────────────────────────────────────────────────────────
hdr(f"6. TPM 簽名測試 (handle {_TPM_HANDLE})")
sig_bytes: bytes | None = None
nonce = os.urandom(32)
if shutil.which("tpm2_sign"):
    env = dict(os.environ)
    if not env.get("TPM2TOOLS_TCTI") and swtpm_marker.exists():
        env["TPM2TOOLS_TCTI"] = "swtpm:host=127.0.0.1,port=2321"

    with tempfile.TemporaryDirectory() as d:
        nonce_f = Path(d) / "nonce.bin"
        sig_f   = Path(d) / "sig.bin"
        nonce_f.write_bytes(nonce)
        base_cmd = [
            "tpm2_sign", "--key-context", _TPM_HANDLE,
            "--hash-algorithm", "sha256", "--scheme", "rsassa",
            "--signature", str(sig_f), str(nonce_f),
        ]
        # 嘗試 --format plain
        r = subprocess.run([*base_cmd[:6], "--format", "plain", *base_cmd[6:]],
                           capture_output=True, timeout=10, env=env)
        if r.returncode == 0 and sig_f.exists():
            sig_bytes = sig_f.read_bytes()
            ok(f"tpm2_sign (--format plain) 成功，簽名長度：{len(sig_bytes)} bytes")
        else:
            sig_f.unlink(missing_ok=True)
            r2 = subprocess.run(base_cmd, capture_output=True, timeout=10, env=env)
            if r2.returncode == 0 and sig_f.exists():
                raw = sig_f.read_bytes()
                # parse TPMT_SIGNATURE: [2B alg][2B hash][2B len][len bytes]
                if len(raw) >= 6:
                    sig_size = int.from_bytes(raw[4:6], "big")
                    if len(raw) >= 6 + sig_size and sig_size > 0:
                        sig_bytes = raw[6:6 + sig_size]
                        ok(f"tpm2_sign (TPMT format) 成功，簽名長度：{len(sig_bytes)} bytes")
                    else:
                        fail(f"TPMT 解析失敗，raw 長度={len(raw)}")
                else:
                    fail(f"TPMT 資料太短：{len(raw)} bytes")
            else:
                fail(f"tpm2_sign 失敗 (rc={r2.returncode})")
                if r2.stderr:
                    info(f"stderr: {r2.stderr.strip()[:300]}")
else:
    fail("tpm2_sign 不可用，無法執行簽名測試")

# ── 7. license.lic ─────────────────────────────────────────────────────────────
hdr("7. license.lic")

def _find_license() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        Path(os.getcwd()) / "system" / "license.lic",
        Path(os.getcwd()) / "license.lic",
        here.parent / "system" / "license.lic",
        here.parent.parent / "system" / "license.lic",
    ]
    for p in candidates:
        if p.exists():
            return p
    # 搜尋常見位置
    for search_root in [Path(os.getcwd()), here.parent.parent]:
        for p in search_root.rglob("license.lic"):
            return p
    return None

lic_path = _find_license()
license_pubkey_pem: str | None = None
if lic_path:
    ok(f"找到：{lic_path}")
    try:
        lic_data = json.loads(lic_path.read_text("utf-8"))
        payload = json.loads(lic_data["payload"])
        info(f"licensee  : {payload.get('licensee', {})}")
        info(f"issuedAt  : {payload.get('issuedAt', '?')}")
        info(f"expiresAt : {payload.get('expiresAt', '(無期限)')}")
        license_pubkey_pem = payload.get("machinePublicKey")
        if license_pubkey_pem:
            b64 = "".join(l for l in license_pubkey_pem.splitlines() if not l.startswith("-----"))
            info(f"machinePublicKey 縮略：{b64[:20]}…{b64[-16:]}")
            fp = hashlib.sha256(license_pubkey_pem.encode()).hexdigest()
            info(f"SHA256(machinePublicKey): {fp}")
        else:
            warn("license 無 machinePublicKey（浮動授權，無 TPM 綁定）")
    except Exception as e:
        fail(f"解析失敗：{e}")
else:
    fail("找不到 license.lic")
    info("搜尋路徑：cwd/license.lic, cwd/system/license.lic")

# ── 8. PEM 比對 ───────────────────────────────────────────────────────────────
hdr("8. PEM 比對（license vs 本機 TPM）")

def _norm_pem(pem: str) -> str:
    return "\n".join(l.strip() for l in pem.strip().splitlines() if l.strip())

if license_pubkey_pem and local_pem:
    if _norm_pem(license_pubkey_pem) == _norm_pem(local_pem):
        ok("license.machinePublicKey == /opt/hiba/tpm/signing_public.pem ✓")
    else:
        fail("license.machinePublicKey ≠ /opt/hiba/tpm/signing_public.pem")
        info("License 是用不同機器的 PEM 簽發的，需重新從本機取得 PEM 並簽發新 license")
elif not license_pubkey_pem:
    warn("license 無 machinePublicKey，跳過比對")
elif not local_pem:
    warn("本機無 signing_public.pem，跳過比對")

if license_pubkey_pem and handle_pem:
    if _norm_pem(license_pubkey_pem) == _norm_pem(handle_pem):
        ok("license.machinePublicKey == TPM handle 公鑰 ✓")
    else:
        fail("license.machinePublicKey ≠ TPM handle 公鑰")
        info("TPM handle 已被重設（重跑 01_tpm_full_setup.sh 後 handle 改變），需重新簽發 license")

# ── 9. 簽名驗證 ───────────────────────────────────────────────────────────────
hdr("9. TPM 簽名驗證（用 license 公鑰驗）")
if sig_bytes and license_pubkey_pem:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding as _pad
        pub = serialization.load_pem_public_key(license_pubkey_pem.encode())
        pub.verify(sig_bytes, nonce, _pad.PKCS1v15(), hashes.SHA256())
        ok("TPM challenge-response 通過 ✓（本機 TPM 握有 license 對應私鑰）")
    except Exception as e:
        fail(f"TPM challenge-response 失敗：{e}")
        info("原因：license 的 machinePublicKey 與本機 TPM handle 的私鑰不對應")
elif not sig_bytes:
    warn("無法取得 TPM 簽名，跳過驗證")
elif not license_pubkey_pem:
    warn("license 無 machinePublicKey，跳過驗證")

# ── 10. issuer 簽名驗證 ───────────────────────────────────────────────────────
hdr("10. Issuer 簽名驗證（license.lic 本身的簽章）")
if lic_path:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.exceptions import InvalidSignature
        import base64 as _b64

        _ISSUER_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAt1wQ/q3fbmYmd8545NJk
/qEyMwtmPRaJFpoALjvxEvrfVIe/H58X1UTkGCept4Ata20HUvr1D8LUsr3jxJUi
48INzbau+HKxwq+fvEaaGPNdgIKZpLOM0TM/g/cdtIvneWsmn4ZEV6q8UTTql7Zp
5mveUc6KY6QWtqEPOxFwVl7RXWxpF/yBu2S0itRdo5ZNkT/70BbJEuL/PAQbuMlw
cb9f08cCqoCsARydnO2znpT6f5mMXodZY/5GJIm3UlcXpSFZWOm3T5Gds46SdRUk
/4X9IffUlLFmHvV0y7sJmQ1WDquDJDuJydls5Y3ByvaokjNdbGhAr9k09QlXy7hy
EwIDAQAB
-----END PUBLIC KEY-----"""

        lic_data = json.loads(lic_path.read_text("utf-8"))
        pub_key = serialization.load_pem_public_key(_ISSUER_PEM.encode())
        pub_key.verify(
            _b64.b64decode(lic_data["signature"]),
            lic_data["payload"].encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )
        ok("Issuer RSA-PSS 簽章驗證通過 ✓")
    except InvalidSignature:
        fail("Issuer 簽章無效 — license.lic 可能被竄改或由不同 Kit Composer 簽發")
    except ImportError:
        warn("cryptography 套件未安裝，跳過 issuer 驗證")
    except Exception as e:
        fail(f"Issuer 驗證錯誤：{e}")

# ── 總結 ──────────────────────────────────────────────────────────────────────
hdr("診斷完成")
print("請將以上完整輸出提供給開發者分析。")
print("重點欄位：第 8 節（PEM 比對）與第 9 節（TPM challenge-response）的結果。")
