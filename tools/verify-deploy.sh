#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# verify-deploy.sh  — 部署驗證腳本（納入安裝包，供部署工程師使用）
#
# 功能：
#   1. 確認後端服務健康
#   2. 顯示機器指紋來源（TPM 2.0 或 /etc/machine-id）
#   3. 輸出 fingerprint 供授權方使用
#   4. 確認授權狀態
#
# 使用方式：
#   bash verify-deploy.sh [--host http://localhost:8000]
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
info() { echo -e "${CYAN}      $1${NC}"; }

HOST="http://localhost:8000"
while [[ $# -gt 0 ]]; do
  case "$1" in --host) HOST="$2"; shift 2;; *) shift;; esac
done

echo ""
echo "════════════════════════════════════════════════"
echo "  Form System Kit — 部署驗證"
echo "  主機：$HOST"
echo "════════════════════════════════════════════════"
echo ""

# ── 1. 健康檢查 ───────────────────────────────────────────────────────────────
HEALTH=$(curl -sf "${HOST}/healthz" 2>/dev/null || echo '{"status":"unreachable"}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "parse_error")

if [[ "$STATUS" == "healthy" ]]; then
  ok "後端服務正常（$HOST）"
  ENV=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('environment','?'))" 2>/dev/null || echo "?")
  info "環境：$ENV"
else
  fail "後端服務不可達（$HOST/healthz → $STATUS）"
  echo ""
  echo "  請確認："
  echo "    docker compose ps"
  echo "    docker logs backend"
  exit 1
fi

# ── 2. 機器指紋 & TPM 狀態 ───────────────────────────────────────────────────
echo ""
echo "── 機器指紋 ─────────────────────────────────────"

# 嘗試不帶 API Key 呼叫（install wizard 提供的端點不需要 auth）
FP_JSON=$(curl -sf "${HOST}/api/machine-id" 2>/dev/null || echo '{"found":false}')
FP_FOUND=$(echo "$FP_JSON"  | python3 -c "import sys,json; print(json.load(sys.stdin).get('found',False))" 2>/dev/null || echo "False")
FP_VAL=$(echo "$FP_JSON"    | python3 -c "import sys,json; print(json.load(sys.stdin).get('fingerprint','')  or '')" 2>/dev/null || echo "")
FP_SRC=$(echo "$FP_JSON"    | python3 -c "import sys,json; print(json.load(sys.stdin).get('source','')       or '')" 2>/dev/null || echo "")
FP_AVAIL=$(echo "$FP_JSON"  | python3 -c "import sys,json; print(json.load(sys.stdin).get('available',False))" 2>/dev/null || echo "False")

if [[ "$FP_FOUND" == "True" && -n "$FP_VAL" ]]; then
  if [[ "$FP_SRC" == "tpm2-ek" ]]; then
    ok "硬體綁定 (TPM 2.0)  ← 最強安全性"
    info "指紋來源：TPM 2.0 Endorsement Key"
  elif [[ "$FP_SRC" == "machine-id" ]]; then
    warn "軟體綁定 (/etc/machine-id)  ← 可被複製，建議安裝 tpm2-tools"
    info "指紋來源：/etc/machine-id"
  else
    info "指紋來源：$FP_SRC"
  fi
  echo ""
  echo "  ┌─────────────────────────────────────────────────────────────────┐"
  echo "  │ 機器指紋（提供給授權方）：                                      │"
  echo "  │  $FP_VAL  │"
  echo "  └─────────────────────────────────────────────────────────────────┘"
else
  warn "無法取得機器指紋（/api/machine-id 未回應或無資料）"
  info "若需機器綁定授權，請確認 install-wizard 已啟動"
fi

# ── 3. 授權狀態（若有 license.lic）──────────────────────────────────────────
echo ""
echo "── 授權狀態 ─────────────────────────────────────"

LIC_FILE="$(dirname "$0")/../license.lic"
if [[ ! -f "$LIC_FILE" ]]; then
  # Try relative to current dir
  LIC_FILE="./license.lic"
fi

if [[ -f "$LIC_FILE" ]]; then
  LIC_EXP=$(python3 -c "
import json, sys
from pathlib import Path
try:
    d = json.loads(Path('$LIC_FILE').read_text('utf-8'))
    payload = json.loads(d['payload'])
    print(payload.get('expiresAt','?'))
except Exception as e:
    print(f'parse_error: {e}')
" 2>/dev/null || echo "?")
  ok "license.lic 存在（到期：$LIC_EXP）"
else
  warn "未找到 license.lic（無機器綁定授權）"
fi

# ── 4. 快速摘要 ───────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
if [[ "$FP_SRC" == "tpm2-ek" ]]; then
  echo -e "  ${GREEN}部署驗證完成 — TPM 2.0 硬體綁定已啟用${NC}"
elif [[ "$FP_FOUND" == "True" ]]; then
  echo -e "  ${YELLOW}部署驗證完成 — 使用軟體綁定（建議升級至 TPM）${NC}"
else
  echo -e "  ${YELLOW}部署驗證完成 — 服務運行中，指紋待確認${NC}"
fi
echo ""
