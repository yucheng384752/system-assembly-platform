#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# test-swtpm-auto.sh  — 驗證 install-wizard swtpm 自動安裝流程
#
# 測試案例：
#   T1  apt-get 安裝 swtpm / swtpm-tools / tpm2-tools / openssl
#   T2  swtpm 手動啟動 + TCP 2321 就緒
#   T3  EK 指紋確定性（同狀態每次相同）
#   T4  Primary Key → Signing Key → Persistent Handle 完整流程
#   T5  swtpm 重啟後指紋不變（模擬重開機）
#   T6  Python _probe_tpm_fingerprint() 透過 swtpm 取得指紋
#   T7  install-wizard _SWTPM_SETUP_SCRIPT 完整執行（跳過 systemd）
#
# 使用方式（在 Docker 容器內）：
#   docker run --rm --privileged ubuntu:22.04 bash /test/test-swtpm-auto.sh
# ──────────────────────────────────────────────────────────────────────────────
set -uo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; SKIP=0

pass() { echo -e "${GREEN}[PASS]${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAIL=$((FAIL+1)); }
skip() { echo -e "${YELLOW}[SKIP]${NC} $1"; SKIP=$((SKIP+1)); }
info() { echo -e "       $1"; }
section() { echo -e "\n── $1 ──────────────────────────────────────────"; }

TPM_STATE="/tmp/test-swtpm-state"
TPM_DIR="/tmp/test-tpm-keys"
HANDLE="0x81000001"
WIZARD_PY="/test/install-wizard.py"

export DEBIAN_FRONTEND=noninteractive

echo ""
echo "══════════════════════════════════════════════════════"
echo "  install-wizard swtpm 自動安裝流程驗證"
echo "══════════════════════════════════════════════════════"

# ── T1: 安裝套件 ──────────────────────────────────────────────────────────────
section "T1: apt-get 安裝 swtpm + tpm2-tools"

apt-get update -qq 2>/dev/null
if apt-get install -y -qq swtpm swtpm-tools tpm2-tools openssl python3 2>/dev/null; then
  for cmd in swtpm swtpm_setup tpm2_createprimary tpm2_createek openssl python3; do
    command -v "$cmd" >/dev/null && pass "$cmd 已安裝" || fail "$cmd 安裝後仍找不到"
  done
else
  fail "apt-get install 失敗"
fi

# ── T2: 啟動 swtpm ────────────────────────────────────────────────────────────
section "T2: swtpm 啟動 + TCP port 2321"

rm -rf "$TPM_STATE" && mkdir -p "$TPM_STATE"
swtpm_setup --tpm2 --tpmstate "$TPM_STATE" --allow-signing --createek 2>/dev/null \
  && pass "swtpm_setup 完成" || fail "swtpm_setup 失敗"

pkill swtpm 2>/dev/null; sleep 1; true
swtpm socket \
  --tpmstate dir="$TPM_STATE" \
  --ctrl type=tcp,port=2322 \
  --server type=tcp,port=2321 \
  --tpm2 --flags startup-clear --daemon 2>/dev/null
sleep 2

if pgrep -x swtpm >/dev/null 2>&1 || python3 -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',2321)); s.close()" 2>/dev/null; then
  pass "swtpm 程序就緒 (port 2321 可連線)"
else
  fail "swtpm 未啟動或 port 2321 無法連線"
fi

export TPM2TOOLS_TCTI="swtpm:host=127.0.0.1,port=2321"
info "TPM2TOOLS_TCTI=${TPM2TOOLS_TCTI}"

# ── T3: EK 指紋確定性 ─────────────────────────────────────────────────────────
section "T3: EK 指紋確定性（同狀態每次相同）"

mkdir -p "$TPM_DIR"
if tpm2_createek -c "${TPM_DIR}/ek1.ctx" -G rsa -u "${TPM_DIR}/ek1.pub" 2>/dev/null; then
  FP1=$(sha256sum "${TPM_DIR}/ek1.pub" | awk '{print $1}')
  info "第 1 次指紋：${FP1:0:16}…"

  if tpm2_createek -c "${TPM_DIR}/ek2.ctx" -G rsa -u "${TPM_DIR}/ek2.pub" 2>/dev/null; then
    FP2=$(sha256sum "${TPM_DIR}/ek2.pub" | awk '{print $1}')
    info "第 2 次指紋：${FP2:0:16}…"
    [[ "$FP1" == "$FP2" ]] \
      && pass "兩次 EK 指紋完全相同（確定性通過）" \
      || fail "兩次 EK 指紋不同（非確定性）"
  else
    fail "第 2 次 tpm2_createek 失敗"
  fi
else
  fail "tpm2_createek 失敗（swtpm 可能未就緒）"
fi

# ── T4: 完整金鑰流程 ──────────────────────────────────────────────────────────
section "T4: Primary → Signing Key → Persistent Handle → 簽章"

# Flush 確保 context 乾淨
tpm2_flushcontext --transient-object 2>/dev/null || true
tpm2_flushcontext --loaded-session   2>/dev/null || true

rm -f "${TPM_DIR}/primary.ctx"
if tpm2_createprimary --hierarchy owner --key-algorithm rsa --hash-algorithm sha256 \
     --key-context "${TPM_DIR}/primary.ctx" 2>/dev/null; then
  pass "Primary Key 建立"
else
  fail "tpm2_createprimary 失敗"; fi

rm -f "${TPM_DIR}/signing.pub" "${TPM_DIR}/signing.priv"
if tpm2_create \
     --parent-context "${TPM_DIR}/primary.ctx" \
     --key-algorithm "rsa2048:rsassa:null" \
     --hash-algorithm sha256 \
     --public  "${TPM_DIR}/signing.pub" \
     --private "${TPM_DIR}/signing.priv" 2>/dev/null; then
  pass "Signing Key 建立"
else
  fail "tpm2_create 失敗"; fi

tpm2_flushcontext --transient-object 2>/dev/null || true
rm -f "${TPM_DIR}/signing.ctx"
if tpm2_load \
     --parent-context "${TPM_DIR}/primary.ctx" \
     --public  "${TPM_DIR}/signing.pub" \
     --private "${TPM_DIR}/signing.priv" \
     --key-context "${TPM_DIR}/signing.ctx" 2>/dev/null; then
  pass "Signing Key 載入"
else
  fail "tpm2_load 失敗"; fi

tpm2_flushcontext --transient-object 2>/dev/null || true
# 清除舊 Handle（若存在）
tpm2_evictcontrol --hierarchy owner --object-context "$HANDLE" "$HANDLE" 2>/dev/null || true
if tpm2_evictcontrol \
     --hierarchy owner \
     --object-context "${TPM_DIR}/signing.ctx" \
     "$HANDLE" 2>/dev/null; then
  pass "持久化至 Handle $HANDLE"
else
  fail "tpm2_evictcontrol 失敗"; fi

# 讀取公鑰
if tpm2_readpublic --object-context "$HANDLE" \
     --output "${TPM_DIR}/signing_public.pem" \
     --format pem 2>/dev/null; then
  pass "公鑰匯出 PEM"
else
  fail "tpm2_readpublic 失敗"; fi

# 簽章測試
echo "hiba-test-$(date +%s)" > /tmp/_hiba_test.txt
tpm2_flushcontext --transient-object 2>/dev/null || true
if tpm2_sign \
     --key-context "$HANDLE" \
     --hash-algorithm sha256 \
     --scheme rsassa \
     --signature /tmp/_hiba_sig.bin \
     /tmp/_hiba_test.txt 2>/dev/null; then
  pass "RSA-2048 簽章測試通過"
else
  fail "tpm2_sign 失敗"
fi
rm -f /tmp/_hiba_test.txt /tmp/_hiba_sig.bin

# ── T5: 重啟後指紋不變 ────────────────────────────────────────────────────────
section "T5: swtpm 重啟後 EK 指紋不變（模擬重開機）"

# 記錄當前指紋
FP_BEFORE=$(sha256sum "${TPM_DIR}/ek1.pub" | awk '{print $1}')

# 停止 swtpm
pkill swtpm 2>/dev/null; sleep 2

# 重新啟動（相同 tpmstate，不加 --overwrite）
swtpm socket \
  --tpmstate dir="$TPM_STATE" \
  --ctrl type=tcp,port=2322 \
  --server type=tcp,port=2321 \
  --tpm2 --flags startup-clear --daemon 2>/dev/null
sleep 2

export TPM2TOOLS_TCTI="swtpm:host=127.0.0.1,port=2321"

# 重新取得 EK
if tpm2_createek -c "${TPM_DIR}/ek3.ctx" -G rsa -u "${TPM_DIR}/ek3.pub" 2>/dev/null; then
  FP_AFTER=$(sha256sum "${TPM_DIR}/ek3.pub" | awk '{print $1}')
  info "重啟前：${FP_BEFORE:0:16}…"
  info "重啟後：${FP_AFTER:0:16}…"
  [[ "$FP_BEFORE" == "$FP_AFTER" ]] \
    && pass "重啟後 EK 指紋不變（持久化成功）" \
    || fail "重啟後 EK 指紋改變（持久化失敗）"
else
  fail "重啟後 tpm2_createek 失敗"
fi

# ── T6: Python _probe_tpm_fingerprint() ──────────────────────────────────────
section "T6: Python _probe_tpm_fingerprint() 透過 swtpm"

if [[ ! -f "$WIZARD_PY" ]]; then
  skip "T6: $WIZARD_PY 未掛載，跳過 Python 整合測試"
else
  FP_PY=$(python3 - <<'PYEOF' 2>/dev/null || echo "ERROR"
import sys, os
sys.path.insert(0, '/test')
# 直接從 install-wizard.py 取得 _probe_tpm_fingerprint 函式
import importlib.util
spec = importlib.util.spec_from_file_location("wizard", "/test/install-wizard.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod._probe_tpm_fingerprint()
print(f"{result['source']}:{result['fingerprint'] or 'NONE'}")
PYEOF
)

  if [[ "$FP_PY" == "ERROR" ]]; then
    fail "Python import install-wizard.py 失敗"
  elif [[ "$FP_PY" == *"tpm2-ek:"* ]]; then
    SRC=$(echo "$FP_PY" | cut -d: -f1)
    FP=$(echo "$FP_PY" | cut -d: -f2)
    pass "_probe_tpm_fingerprint() 回傳 TPM EK 指紋（source=${SRC}）"
    info "指紋：${FP:0:16}…"
    # 比較與 bash 取得的指紋是否一致
    [[ "${FP:0:16}" == "${FP_AFTER:0:16}" ]] \
      && pass "Python 指紋與 bash 取得的 EK 指紋一致" \
      || fail "Python 指紋與 bash EK 指紋不一致"
  else
    fail "_probe_tpm_fingerprint() 未使用 swtpm（回傳：${FP_PY}）"
  fi
fi

# ── T7: 內嵌腳本 _SWTPM_SETUP_SCRIPT 執行（跳過 systemd 區段）────────────────
section "T7: install-wizard _SWTPM_SETUP_SCRIPT 擷取並執行（無 systemd）"

if [[ ! -f "$WIZARD_PY" ]]; then
  skip "T7: $WIZARD_PY 未掛載"
else
  # 從 install-wizard.py 擷取 _SWTPM_SETUP_SCRIPT 並注入 SKIP_SYSTEMD=1
  EXTRACTED=$(python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('w', '$WIZARD_PY')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(mod._SWTPM_SETUP_SCRIPT)
" 2>/dev/null)

  if [[ -z "$EXTRACTED" ]]; then
    fail "_SWTPM_SETUP_SCRIPT 無法從 install-wizard.py 取出"
  else
    pass "_SWTPM_SETUP_SCRIPT 成功從 install-wizard.py 取出（${#EXTRACTED} chars）"

    # 建立注入 SKIP_SYSTEMD 的版本：
    #   - daemon-reload / enable → echo SKIP
    #   - restart swtpm.service → 實際啟動 swtpm（使用正確 state 路徑）
    #   - is-active check → true
    #   - hiba-subweb check → true
    PATCHED=$(echo "$EXTRACTED" \
      | sed 's/systemctl daemon-reload/echo "[SKIP] systemctl daemon-reload"/g' \
      | sed 's/systemctl enable swtpm\.service/echo "[SKIP] systemctl enable"/g' \
      | sed 's|systemctl restart swtpm\.service|pkill swtpm 2>/dev/null; sleep 1; swtpm socket --tpmstate dir=/opt/hiba/tpm/swtpm-state --ctrl type=tcp,port=2322 --server type=tcp,port=2321 --tpm2 --flags startup-clear --daemon 2>/dev/null; sleep 2|g' \
      | sed 's/systemctl is-active --quiet swtpm\.service/true/g' \
      | sed 's/systemctl is-enabled hiba-subweb\.service.*/true/g' \
      | sed 's|ss -tlnp.*grep -q "2321"|pgrep -x swtpm \>/dev/null|g')

    # 寫入暫存並執行
    SCRIPT_TMP=$(mktemp /tmp/swtpm_test_XXXXXX.sh)
    echo "$PATCHED" > "$SCRIPT_TMP"
    chmod +x "$SCRIPT_TMP"

    # 重設 TPM state 以測試首次安裝（殺掉 T5 留下的舊 swtpm）
    pkill swtpm 2>/dev/null; sleep 1; true
    rm -rf /opt/hiba
    export SUDO_USER="testuser"

    if bash "$SCRIPT_TMP" 2>&1 | grep -E "^\[TPM\]|^\[SKIP\]|STAGE|✓|✗|Fingerprint" | head -50; then
      # 確認腳本成功結果
      [[ -f "/opt/hiba/tpm/swtpm-state/.initialized" ]] \
        && pass "swtpm-state/.initialized 標記存在（冪等保護）" \
        || fail ".initialized 標記不存在"
      [[ -f "/opt/hiba/tpm/ek_fingerprint.txt" ]] \
        && pass "ek_fingerprint.txt 已產生" \
        || fail "ek_fingerprint.txt 不存在"
      if [[ -f "/opt/hiba/tpm/ek_fingerprint.txt" ]]; then
        FP_FILE=$(cat /opt/hiba/tpm/ek_fingerprint.txt)
        info "Fingerprint: ${FP_FILE:0:16}…"
      fi
    else
      fail "_SWTPM_SETUP_SCRIPT 執行失敗"
    fi
    rm -f "$SCRIPT_TMP"
  fi
fi

# ── 摘要 ──────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  測試結果"
echo "══════════════════════════════════════════════════════"
echo -e "  ${GREEN}通過${NC}: $PASS   ${RED}失敗${NC}: $FAIL   ${YELLOW}跳過${NC}: $SKIP"
echo ""
[[ $FAIL -gt 0 ]] \
  && echo -e "  ${RED}有測試失敗，請查看上方說明。${NC}" \
  || echo -e "  ${GREEN}所有測試通過（或已知跳過）。${NC}"
echo ""
exit $FAIL
