"""
test_license_roundtrip.py — 驗證 issuer 私鑰簽發的 license 能被 license.py 驗證通過。

模擬完整流程：
  1. 用 signing-private-key.pem 簽發 license payload (RSA-PSS)  ← serve-gui.cjs 做的事
  2. 用 license.py 內嵌的 _PUBLIC_KEY_PEM 驗證簽名              ← 後端啟動時做的事
"""
import base64
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

ROOT = Path(__file__).resolve().parents[1]
PRIV = ROOT / "tools" / "keys" / "signing-private-key.pem"
LICENSE_PY = ROOT / "dist" / "client-deploy-gui-selected-form-system" / "system" / "backend" / "app" / "core" / "license.py"

PASS = FAIL = 0
def ok(m):   global PASS; PASS += 1; print(f"  [PASS] {m}")
def fail(m): global FAIL; FAIL += 1; print(f"  [FAIL] {m}")

print("=" * 60)
print("  License Roundtrip Test")
print("=" * 60)

# 1. 私鑰存在
if PRIV.exists():
    ok(f"issuer 私鑰存在：{PRIV.name}")
else:
    fail(f"issuer 私鑰不存在，請先執行 tools/generate-license-keys.ps1")
    sys.exit(1)

# 2. 從 license.py 抽出內嵌公鑰
src = LICENSE_PY.read_text("utf-8")
m = re.search(r'_PUBLIC_KEY_PEM = """\s*(-----BEGIN PUBLIC KEY-----.*?-----END PUBLIC KEY-----)\s*"""', src, re.DOTALL)
if m:
    embedded_pub = m.group(1)
    ok("從 license.py 抽出 _PUBLIC_KEY_PEM")
else:
    fail("license.py 找不到 _PUBLIC_KEY_PEM")
    sys.exit(1)

# 3. 確認 issuer 私鑰 ↔ 內嵌公鑰是同一對
priv_key = serialization.load_pem_private_key(PRIV.read_bytes(), password=None)
derived_pub = priv_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode().strip()
if derived_pub == embedded_pub.strip():
    ok("issuer 私鑰 ↔ license.py 內嵌公鑰 配對正確")
else:
    fail("私鑰與內嵌公鑰不匹配！license 驗證會失敗")

# 4. 模擬 serve-gui.cjs 簽發 license（透過 node + crypto，確保簽名格式一致）
node_sign = r'''
const crypto = require("crypto");
const fs = require("fs");
const priv = fs.readFileSync(process.argv[1], "utf8");
const payload = process.argv[2];
const signer = crypto.createSign("RSA-SHA256");
signer.update(payload, "utf8");
signer.end();
const sig = signer.sign({
  key: priv,
  padding: crypto.constants.RSA_PKCS1_PSS_PADDING,
  saltLength: crypto.constants.RSA_PSS_SALTLEN_DIGEST,
}, "base64");
process.stdout.write(sig);
'''

# 模擬 machine TPM 公鑰（任意 RSA 公鑰即可，這裡只測 license 簽名層）
fake_machine_pub = priv_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

payload_obj = {
    "licensee": {"name": "Test Co", "email": "test@example.com"},
    "machinePublicKey": fake_machine_pub,
    "issuedAt": datetime.now(timezone.utc).isoformat(),
    "expiresAt": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
}
payload_str = json.dumps(payload_obj)

try:
    sig_b64 = subprocess.check_output(
        ["node", "-e", node_sign, str(PRIV), payload_str],
        text=True, timeout=15,
    ).strip()
    ok(f"node 簽發 license 簽名成功（{len(sig_b64)} chars）")
except Exception as e:
    fail(f"node 簽發失敗：{e}")
    sys.exit(1)

# 5. 用內嵌公鑰驗證簽名（複製 license.py verify_license 的核心邏輯）
try:
    pub_key = serialization.load_pem_public_key(embedded_pub.encode())
    pub_key.verify(
        base64.b64decode(sig_b64),
        payload_str.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    ok("license.py RSA-PSS 驗簽通過（issuer 簽發 ↔ 後端驗證 相容）")
except InvalidSignature:
    fail("RSA-PSS 驗簽失敗 — 簽名格式不相容")
except Exception as e:
    fail(f"驗簽錯誤：{e}")

# 6. 過期檢查
expires = datetime.fromisoformat(payload_obj["expiresAt"])
if datetime.now(timezone.utc) < expires:
    ok(f"license 未過期（到期：{payload_obj['expiresAt'][:10]}）")
else:
    fail("license 已過期")

print(f"\n{'='*60}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
