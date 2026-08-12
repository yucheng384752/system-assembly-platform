"""
test_license_runtime_tpm.py — 驗證後端 license.py 在 TPM2TOOLS_TCTI 未設定時，
仍能靠 swtpm marker 自動注入 TCTI 完成 TPM 挑戰-回應。
重現後端進程情境（未繼承 /etc/profile.d 的 TCTI）。
前置：swtpm 已佈建，handle 0x81000001 已持久化。在 Docker 內執行。
"""
import importlib.util
import os
import sys
from pathlib import Path

PASS = FAIL = 0
def ok(m):   global PASS; PASS += 1; print(f"  [PASS] {m}")
def fail(m): global FAIL; FAIL += 1; print(f"  [FAIL] {m}")

print("=" * 60)
print("  License Runtime TPM (auto-TCTI) Test")
print("=" * 60)

# 關鍵：清掉 TPM2TOOLS_TCTI，模擬後端進程未繼承 TCTI 的情境
os.environ.pop("TPM2TOOLS_TCTI", None)
ok("已清除 os.environ['TPM2TOOLS_TCTI']（重現後端進程情境）")

# swtpm marker 應存在（由 01_tpm_full_setup.sh 建立）
marker = Path("/opt/hiba/tpm/swtpm-state/.initialized")
if marker.exists():
    ok("swtpm marker 存在 (.initialized)")
else:
    fail("swtpm marker 不存在 — swtpm 未佈建")
    sys.exit(1)

# 載入 license.py
LIC = Path("/src/dist/client-deploy-gui-selected-form-system/system/backend/app/core/license.py")
spec = importlib.util.spec_from_file_location("license_mod", LIC)
lic = importlib.util.module_from_spec(spec)
sys.modules["license_mod"] = lic  # dataclass 需能在 sys.modules 找到模組
spec.loader.exec_module(lic)
ok("載入 license.py 模組")

# 1. _tpm_subprocess_env 應自動注入 TCTI
env = lic._tpm_subprocess_env()
if env.get("TPM2TOOLS_TCTI") == "swtpm:host=127.0.0.1,port=2321":
    ok("_tpm_subprocess_env() 自動注入 swtpm TCTI")
else:
    fail(f"未自動注入 TCTI：{env.get('TPM2TOOLS_TCTI')}")

# 2. 讀取 swtpm 簽名公鑰
pem_path = Path("/opt/hiba/tpm/signing_public.pem")
if not pem_path.exists():
    fail("signing_public.pem 不存在")
    sys.exit(1)
pubkey_pem = pem_path.read_text("utf-8")
ok("讀取 signing_public.pem")

# 3. 核心：_verify_tpm_possession 在無 TCTI env 下應成功（靠自動注入）
result = lic._verify_tpm_possession(pubkey_pem)
if result:
    ok("_verify_tpm_possession() 成功 — 後端無 TCTI 也能完成 TPM 挑戰-回應")
else:
    fail("_verify_tpm_possession() 失敗 — TPM 驗證未通過")

# 4. 反例：用錯誤公鑰應失敗（確保不是永遠回 True）
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
wrong_pem = wrong.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()
if not lic._verify_tpm_possession(wrong_pem):
    ok("錯誤公鑰正確被拒（挑戰-回應有實際驗證）")
else:
    fail("錯誤公鑰竟通過 — 驗證邏輯有誤")

print(f"\n{'='*60}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
