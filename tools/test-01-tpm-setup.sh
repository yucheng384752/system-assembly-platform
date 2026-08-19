#!/usr/bin/env bash
# ============================================================
# test-01-tpm-setup.sh — 在 Docker (Ubuntu 22.04) 內測試
#   C:\Users\gslab\Desktop\files\scripts_pi\deploy_http\01_tpm_full_setup.sh
#
# 注意：容器無 systemd，以 fake systemctl stub 取代，
#       讓 swtpm 直接以 socket daemon 模式啟動。
# ============================================================
set -uo pipefail

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  [PASS] $1"; }
fail() { FAIL=$((FAIL+1)); echo "  [FAIL] $1"; }
section() { echo ""; echo "=== $1 ==="; }

TPM_DIR="/opt/hiba/tpm"
TPM_STATE="${TPM_DIR}/swtpm-state"
SWTPM_LOG="${TPM_DIR}/swtpm.log"
HANDLE="0x81000001"

# ── Fake systemctl（取代 systemd 服務管理） ──────────────────
install_fake_systemctl() {
cat > /usr/local/bin/systemctl <<'SYSCTL'
#!/usr/bin/env bash
args="$*"
TPM_STATE="/opt/hiba/tpm/swtpm-state"
SWTPM_LOG="/opt/hiba/tpm/swtpm.log"

case "$args" in
  *"daemon-reload"*)
    echo "[DOCKER-SKIP] systemctl daemon-reload" ;;
  *"enable swtpm"*)
    echo "[DOCKER-SKIP] systemctl enable swtpm.service" ;;
  *"restart swtpm"*)
    # 實際啟動 swtpm daemon
    pkill -x swtpm 2>/dev/null || true
    sleep 1
    /usr/bin/swtpm socket \
      --tpmstate dir="${TPM_STATE}" \
      --ctrl type=tcp,port=2322 \
      --server type=tcp,port=2321 \
      --tpm2 --flags startup-clear --daemon \
      --log "file=${SWTPM_LOG},level=5"
    sleep 2
    echo "[DOCKER] swtpm socket daemon started" ;;
  *"is-active --quiet swtpm"*)
    pgrep -x swtpm >/dev/null 2>&1 ;;
  *"is-active swtpm"*)
    if pgrep -x swtpm >/dev/null 2>&1; then
      echo "active"; exit 0
    else
      echo "inactive"; exit 1
    fi ;;
  *"is-enabled swtpm"*)
    echo "enabled"; exit 0 ;;
  *"is-enabled hiba-subweb"*)
    echo "disabled"; exit 1 ;;
  *"restart hiba-subweb"*)
    echo "[DOCKER-SKIP] restart hiba-subweb" ;;
  *"journalctl"*)
    echo "[DOCKER-SKIP] journalctl $args" ;;
  *)
    echo "[DOCKER-STUB] systemctl $args" ;;
esac
SYSCTL
chmod +x /usr/local/bin/systemctl
echo "  fake systemctl installed"
}

section "SETUP: 安裝 fake systemctl"
install_fake_systemctl
ok "fake systemctl 已就位"

# ── 執行 01_tpm_full_setup.sh ───────────────────────────────
section "RUN: bash /test/01_tpm_full_setup.sh"
export TPM2TOOLS_TCTI="swtpm:host=127.0.0.1,port=2321"
set +e
bash /test/01_tpm_full_setup.sh 2>&1
SCRIPT_RC=$?
set -e

section "VERIFY: 結果驗證"

# V1: 腳本回傳值
if [[ $SCRIPT_RC -eq 0 ]]; then
  ok "V1 腳本正常結束 (exit 0)"
else
  fail "V1 腳本異常結束 (exit $SCRIPT_RC)"
fi

# V2: .initialized marker
if [[ -f "${TPM_STATE}/.initialized" ]]; then
  ok "V2 .initialized marker 存在"
else
  fail "V2 .initialized marker 不存在"
fi

# V3: signing_public.pem
if [[ -f "${TPM_DIR}/signing_public.pem" ]] && grep -q "BEGIN PUBLIC KEY" "${TPM_DIR}/signing_public.pem" 2>/dev/null; then
  ok "V3 signing_public.pem 存在且格式正確"
else
  fail "V3 signing_public.pem 不存在或格式錯誤"
fi

# V4: handle 0x81000001 持久化
HANDLES=$(TPM2TOOLS_TCTI="swtpm:host=127.0.0.1,port=2321" tpm2_getcap handles-persistent 2>/dev/null || echo "")
if echo "$HANDLES" | grep -q "$HANDLE"; then
  ok "V4 Handle $HANDLE 已持久化"
else
  fail "V4 Handle $HANDLE 不存在（handles: ${HANDLES:-none}）"
fi

# V5: ek_fingerprint.txt
if [[ -f "${TPM_DIR}/ek_fingerprint.txt" ]] && [[ -s "${TPM_DIR}/ek_fingerprint.txt" ]]; then
  FP=$(cat "${TPM_DIR}/ek_fingerprint.txt")
  ok "V5 ek_fingerprint.txt 存在：${FP:0:16}…"
else
  fail "V5 ek_fingerprint.txt 不存在或空白"
fi

# V6: TPM 簽章測試（完整 PKI 流程驗證）
section "V6: TPM 簽章驗證（PKI challenge-response 模擬）"
NONCE_FILE=$(mktemp)
SIG_FILE=$(mktemp)
printf '%032d' $RANDOM > "$NONCE_FILE"

set +e
TPM2TOOLS_TCTI="swtpm:host=127.0.0.1,port=2321" \
  tpm2_sign \
    --key-context "$HANDLE" \
    --hash-algorithm sha256 \
    --scheme rsassa \
    --format plain \
    --signature "$SIG_FILE" \
    "$NONCE_FILE" 2>/dev/null
SIGN_RC=$?
set -e

if [[ $SIGN_RC -eq 0 ]] && [[ -s "$SIG_FILE" ]]; then
  # 用 openssl 驗簽
  if openssl dgst -sha256 -verify "${TPM_DIR}/signing_public.pem" \
       -signature "$SIG_FILE" "$NONCE_FILE" 2>/dev/null; then
    ok "V6 TPM 簽章 + openssl 驗簽通過（PKI 挑戰-回應 OK）"
  else
    # --format plain 可能不支援，改試 TPMT_SIGNATURE 解析
    TPM2TOOLS_TCTI="swtpm:host=127.0.0.1,port=2321" \
      tpm2_sign --key-context "$HANDLE" --hash-algorithm sha256 \
        --scheme rsassa --signature "$SIG_FILE" "$NONCE_FILE" 2>/dev/null || true
    # 用 python3 解析 TPMT_SIGNATURE
    PY_VERIFY=$(python3 - <<PYEOF 2>/dev/null
import sys, hashlib
from pathlib import Path
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    sig_raw = Path("$SIG_FILE").read_bytes()
    # parse TPMT_SIGNATURE: [2B alg][2B hash][2B size][size bytes]
    if len(sig_raw) >= 6:
        sz = int.from_bytes(sig_raw[4:6], 'big')
        raw_sig = sig_raw[6:6+sz]
    else:
        sys.exit(1)
    pub = serialization.load_pem_public_key(Path("${TPM_DIR}/signing_public.pem").read_bytes())
    nonce = Path("$NONCE_FILE").read_bytes()
    pub.verify(raw_sig, nonce, padding.PKCS1v15(), hashes.SHA256())
    print("OK")
except Exception as e:
    print(f"FAIL:{e}", file=sys.stderr)
    sys.exit(1)
PYEOF
    )
    if [[ "$PY_VERIFY" == "OK" ]]; then
      ok "V6 TPM 簽章驗證通過（TPMT_SIGNATURE 解析）"
    else
      fail "V6 簽章驗證失敗（plain/TPMT_SIGNATURE 均不通過）"
    fi
  fi
else
  fail "V6 tpm2_sign 失敗（exit $SIGN_RC）"
fi

rm -f "$NONCE_FILE" "$SIG_FILE"

# V7: 冪等性（重複執行不破壞指紋）
section "V7: 冪等性測試（二次執行不重建狀態）"
FP_BEFORE=$(cat "${TPM_DIR}/ek_fingerprint.txt" 2>/dev/null || echo "NONE")
set +e
bash /test/01_tpm_full_setup.sh 2>&1 | grep -E "↷|SKIP|STAGE|✓|✗" || true
set -e
FP_AFTER=$(cat "${TPM_DIR}/ek_fingerprint.txt" 2>/dev/null || echo "NONE2")
if [[ "$FP_BEFORE" == "$FP_AFTER" ]] && [[ "$FP_BEFORE" != "NONE" ]]; then
  ok "V7 二次執行後指紋不變（${FP_BEFORE:0:16}…）"
else
  fail "V7 二次執行後指紋改變或消失（before=${FP_BEFORE:0:16}, after=${FP_AFTER:0:16}）"
fi

# ── 最終摘要 ─────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  PASS: $PASS  FAIL: $FAIL"
echo "============================================================"
[[ $FAIL -eq 0 ]]
