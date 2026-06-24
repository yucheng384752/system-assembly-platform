#!/usr/bin/env python3
"""
Form System 安裝精靈 (Install Wizard)
──────────────────────────────────────
Local web-based installer. No external runtime dependencies needed.

Usage:
    python3 install-wizard.py              # auto-detect system dir
    python3 install-wizard.py /path/sys    # specify system directory
    python3 install-wizard.py --port 9981  # custom port

Opens http://localhost:9981/ automatically.
"""
from __future__ import annotations

import http.server
import json
import os
import platform
import secrets as _secrets_mod
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
_DEFAULT_PORT = 9981
_HERE = Path(__file__).parent.resolve()

# ── Embedded persistent swtpm setup script ────────────────────────────────────
# 當偵測到沒有硬體 TPM 時，由 _setup_swtpm_linux() 寫入磁碟並執行
_SWTPM_SETUP_SCRIPT = r"""#!/usr/bin/env bash
# 01_tpm_full_setup.sh — 持久化 swtpm 初始化（由 install-wizard 自動執行）
set -uo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[TPM] ✓ $1${NC}"; }
err()  { echo -e "${RED}[TPM] ✗ $1${NC}"; }
info() { echo -e "${YELLOW}[TPM] ▸ $1${NC}"; }
skip() { echo -e "${CYAN}[TPM] ↷ $1（已存在，跳過）${NC}"; }
die()  { err "$1"; exit 1; }

TPM_DIR="/opt/hiba/tpm"
TPM_STATE="${TPM_DIR}/swtpm-state"
HANDLE="0x81000001"
TCTI_ENV_FILE="/etc/profile.d/hiba-tpm.sh"
SWTPM_SERVICE="/etc/systemd/system/swtpm.service"
TCTI_CONF="${TPM_DIR}/tcti.conf"
SWTPM_LOG="${TPM_DIR}/swtpm.log"
TCTI_VALUE="swtpm:host=127.0.0.1,port=2321"

REAL_USER="${SUDO_USER:-${USER:-$(logname 2>/dev/null || whoami)}}"

info "STAGE 0：前置確認"
[[ $EUID -eq 0 ]] || die "需要 root 權限（請以 sudo 執行安裝精靈）"
for cmd in swtpm swtpm_setup tpm2_createprimary tpm2_create tpm2_load \
           tpm2_evictcontrol tpm2_readpublic tpm2_flushcontext openssl; do
  command -v "$cmd" >/dev/null 2>&1 && ok "$cmd" || die "$cmd 未找到"
done

mkdir -p "$TPM_DIR" "$TPM_STATE"
chown -R "$REAL_USER":"$REAL_USER" "$TPM_DIR"
chmod 700 "$TPM_STATE"
ok "目錄：$TPM_DIR"

info "STAGE 1：swtpm 狀態初始化（冪等）"
STATE_MARKER="${TPM_STATE}/.initialized"
if [[ -f "$STATE_MARKER" ]]; then
  skip "swtpm 狀態已存在，指紋維持不變"
else
  swtpm_setup --tpm2 --tpmstate "$TPM_STATE" --allow-signing --createek \
    2>>"$SWTPM_LOG" || die "swtpm_setup 失敗，查看：$SWTPM_LOG"
  touch "$STATE_MARKER"
  chown "$REAL_USER":"$REAL_USER" "$STATE_MARKER"
  ok "swtpm 狀態初始化完成（EK 已固定）"
fi

info "STAGE 2：swtpm systemd 服務"
cat > "$TCTI_CONF" <<TCTIEOF
TPM2TOOLS_TCTI=${TCTI_VALUE}
TCTIEOF
chmod 644 "$TCTI_CONF"
ok "TCTI 設定：$TCTI_CONF"

if [[ ! -f "$SWTPM_SERVICE" ]]; then
  cat > "$SWTPM_SERVICE" <<SVCEOF
[Unit]
Description=Software TPM (swtpm) for HiBA-AB / Form System
After=network.target
Before=hiba-subweb.service

[Service]
Type=forking
User=root
ExecStartPre=/bin/mkdir -p ${TPM_STATE}
ExecStart=/usr/bin/swtpm socket \\
  --tpmstate dir=${TPM_STATE} \\
  --ctrl type=tcp,port=2322 \\
  --server type=tcp,port=2321 \\
  --tpm2 --flags startup-clear --daemon \\
  --log file=${SWTPM_LOG},level=5
ExecStop=/usr/bin/pkill -f "swtpm socket"
RemainAfterExit=yes
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
SVCEOF
  ok "swtpm.service 建立完成"
else
  skip "swtpm.service"
fi

systemctl daemon-reload
systemctl enable swtpm.service
systemctl restart swtpm.service
sleep 2
systemctl is-active --quiet swtpm.service || { journalctl -u swtpm.service -n 10 --no-pager; die "swtpm.service 啟動失敗"; }
ok "swtpm.service 運行中（開機自啟）"
ss -tlnp 2>/dev/null | grep -q "2321" || die "swtpm port 2321 未就緒"
ok "TCP port 2321 就緒"

info "STAGE 3：全域環境變數"
cat > "$TCTI_ENV_FILE" <<ENVEOF
# HiBA-AB / Form System swtpm TCTI
export TPM2TOOLS_TCTI="${TCTI_VALUE}"
ENVEOF
chmod 644 "$TCTI_ENV_FILE"
export TPM2TOOLS_TCTI="$TCTI_VALUE"
ok "環境變數：$TCTI_ENV_FILE"

SUBWEB_ENV="/opt/hiba/subweb/.env"
if [[ -f "$SUBWEB_ENV" ]]; then
  sed -i '/^TPM2TOOLS_TCTI/d' "$SUBWEB_ENV"
  echo "TPM2TOOLS_TCTI=${TCTI_VALUE}" >> "$SUBWEB_ENV"
  ok "hiba-subweb .env 更新"
fi

info "STAGE 4：清空 TPM context"
sudo -E tpm2_clear --hierarchy owner 2>/dev/null || \
  sudo -E tpm2_clear -c o 2>/dev/null || \
  sudo -E tpm2_clear 2>/dev/null || err "tpm2_clear 失敗（非致命）"

info "STAGE 5：建立 Primary Key"
rm -f "${TPM_DIR}/primary.ctx"
tpm2_createprimary --hierarchy owner --key-algorithm rsa --hash-algorithm sha256 \
  --key-context "${TPM_DIR}/primary.ctx" || die "tpm2_createprimary 失敗"
[[ -s "${TPM_DIR}/primary.ctx" ]] && ok "primary.ctx" || die "primary.ctx 為空"

info "STAGE 6：建立 RSA-2048 Signing Key"
rm -f "${TPM_DIR}/signing.pub" "${TPM_DIR}/signing.priv"
tpm2_create \
  --parent-context "${TPM_DIR}/primary.ctx" \
  --key-algorithm "rsa2048:rsassa:null" \
  --hash-algorithm sha256 \
  --public  "${TPM_DIR}/signing.pub" \
  --private "${TPM_DIR}/signing.priv" || die "tpm2_create 失敗"
[[ -s "${TPM_DIR}/signing.pub" ]]  && ok "signing.pub"  || die "signing.pub 不存在"
[[ -s "${TPM_DIR}/signing.priv" ]] && ok "signing.priv" || die "signing.priv 不存在"

info "STAGE 7：載入並持久化至 $HANDLE"
tpm2_flushcontext --transient-object 2>/dev/null || true
tpm2_flushcontext --loaded-session   2>/dev/null || true
tpm2_flushcontext --saved-session    2>/dev/null || true
rm -f "${TPM_DIR}/signing.ctx"
tpm2_load \
  --parent-context "${TPM_DIR}/primary.ctx" \
  --public  "${TPM_DIR}/signing.pub" \
  --private "${TPM_DIR}/signing.priv" \
  --key-context "${TPM_DIR}/signing.ctx" || die "tpm2_load 失敗"
[[ -s "${TPM_DIR}/signing.ctx" ]] && ok "signing.ctx" || die "signing.ctx 不存在"
tpm2_flushcontext --transient-object 2>/dev/null || true
tpm2_evictcontrol --hierarchy owner --object-context "$HANDLE" "$HANDLE" 2>/dev/null && \
  echo "[TPM] (舊 Handle 已清除)" || true
tpm2_evictcontrol --hierarchy owner --object-context "${TPM_DIR}/signing.ctx" \
  "$HANDLE" || die "tpm2_evictcontrol 失敗"
ok "持久化完成：$HANDLE"

info "STAGE 8：匯出公鑰與 EK Fingerprint"
tpm2_flushcontext --transient-object 2>/dev/null || true
tpm2_flushcontext --loaded-session   2>/dev/null || true
tpm2_readpublic --object-context "$HANDLE" \
  --output "${TPM_DIR}/signing_public.pem" --format pem || die "tpm2_readpublic 失敗"
ok "公鑰：${TPM_DIR}/signing_public.pem"
EK_FP=$(openssl pkey -in "${TPM_DIR}/signing_public.pem" -pubin -outform DER 2>/dev/null \
  | sha256sum | awk '{print $1}')
echo "$EK_FP" > "${TPM_DIR}/ek_fingerprint.txt"
chown "$REAL_USER":"$REAL_USER" "${TPM_DIR}/ek_fingerprint.txt"
ok "EK Fingerprint：$EK_FP"

info "STAGE 9：最終驗證 + 簽章測試"
tpm2_flushcontext --transient-object 2>/dev/null || true
tpm2_flushcontext --loaded-session   2>/dev/null || true
tpm2_getcap handles-persistent 2>/dev/null | grep -q "$HANDLE" && \
  ok "Handle $HANDLE 確認存在" || die "Handle 不在清單中"
echo "hiba-test" > /tmp/_hiba_test.txt
tpm2_sign --key-context "$HANDLE" --hash-algorithm sha256 --scheme rsassa \
  --signature /tmp/_hiba_sig.bin /tmp/_hiba_test.txt 2>/dev/null && \
  ok "簽章測試通過" || err "簽章測試失敗（非致命）"
rm -f /tmp/_hiba_test.txt /tmp/_hiba_sig.bin

systemctl is-enabled hiba-subweb.service 2>/dev/null | grep -q "enabled" && \
  systemctl restart hiba-subweb.service && ok "hiba-subweb.service 已重啟" || true

echo ""
echo "========================================================"
echo "[TPM] swtpm 持久化初始化完成"
echo "  Fingerprint : $EK_FP"
echo "  State       : $TPM_STATE（開機保留）"
echo "  TCTI        : $TCTI_VALUE"
echo "========================================================"
"""

# ── Global state ──────────────────────────────────────────────────────────────
_lock = threading.Lock()
_install_state: dict = {
    "running": False,
    "log": [],
    "step_idx": -1,
    "success": None,
}
_sys_root_hint: Path | None = None
_last_heartbeat: float = 0.0  # epoch seconds; 0 = no heartbeat yet (watchdog inactive)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_sys_root() -> Path | None:
    if _sys_root_hint is not None:
        return _sys_root_hint
    for name in ("system", "generated-system"):
        c = _HERE / name
        if (c / "backend" / "requirements.txt").exists():
            return c
    return None


def _read_recipe() -> dict:
    p = _HERE / "recipe.json"
    if not p.exists():
        return {"name": "unknown", "enabledKits": [], "database": {"engine": "postgresql"}}
    raw = p.read_bytes()
    text = raw[3:].decode("utf-8") if raw[:3] == b"\xef\xbb\xbf" else raw.decode("utf-8")
    return json.loads(text)


def _generate_secret() -> str:
    return _secrets_mod.token_urlsafe(48)


_TPM_SIGNING_HANDLE  = "0x81000001"
_TPM_SIGNING_PEM_PATH = Path("/opt/hiba/tpm/signing_public.pem")


def _probe_tpm_signing_pubkey() -> dict:
    """
    Returns {'source': 'tpm2-signing-key'|'none', 'pubkey_pem': str|None}
    Reads the TPM signing public key (RSA-2048 PEM). No machine-id fallback.
    Priority:
      1. /opt/hiba/tpm/signing_public.pem  (pre-built by 01_tpm_full_setup.sh)
      2. tpm2_readpublic on handle 0x81000001 (on-demand export, Linux only)
    """
    # 1. Read pre-built signing_public.pem from swtpm/TPM setup script
    if _TPM_SIGNING_PEM_PATH.exists():
        try:
            pem = _TPM_SIGNING_PEM_PATH.read_text("utf-8").strip()
            if "BEGIN PUBLIC KEY" in pem:
                return {"source": "tpm2-signing-key", "pubkey_pem": pem}
        except Exception:
            pass

    # 2. Export from TPM handle on-demand (Linux)
    if platform.system() == "Linux":
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                pem_path = Path(tmpdir) / "signing.pem"
                r = subprocess.run(
                    ["tpm2_readpublic", "--object-context", _TPM_SIGNING_HANDLE,
                     "--output", str(pem_path), "--format", "pem"],
                    capture_output=True, timeout=10,
                )
                if r.returncode == 0 and pem_path.exists():
                    pem = pem_path.read_text("utf-8").strip()
                    if "BEGIN PUBLIC KEY" in pem:
                        return {"source": "tpm2-signing-key", "pubkey_pem": pem}
        except Exception:
            pass

    return {"source": "none", "pubkey_pem": None}


def _wizard_tpm_sign_nonce(nonce: bytes) -> bytes | None:
    """
    Ask TPM handle 0x81000001 to sign a nonce (RSASSA-PKCS1v15-SHA256).
    Returns raw RSA signature bytes, or None if TPM is unavailable.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        nonce_path = Path(tmpdir) / "nonce.bin"
        sig_path   = Path(tmpdir) / "sig.bin"
        nonce_path.write_bytes(nonce)
        base_cmd = [
            "tpm2_sign",
            "--key-context", _TPM_SIGNING_HANDLE,
            "--hash-algorithm", "sha256",
            "--scheme", "rsassa",
            "--signature", str(sig_path),
            str(nonce_path),
        ]
        # Try --format plain first (tpm2-tools >= 4.x)
        for extra in (["--format", "plain"], []):
            try:
                r = subprocess.run(
                    [*base_cmd[:6], *extra, *base_cmd[6:]],
                    capture_output=True, timeout=10,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
                return None
            if r.returncode == 0 and sig_path.exists():
                raw = sig_path.read_bytes()
                if extra:
                    return raw
                # Parse TPMT_SIGNATURE: [2B alg][2B hash][2B size][size bytes sig]
                if len(raw) >= 6:
                    sz = int.from_bytes(raw[4:6], "big")
                    if len(raw) >= 6 + sz and sz > 0:
                        return raw[6:6 + sz]
            sig_path.unlink(missing_ok=True)
    return None


def _setup_tpm_linux(log_fn, sys_root: Path) -> None:
    """Install tpm2-tools, provision TPM signing key, export machine-pubkey.pem. Best-effort."""
    import shutil

    # 提早偵測 root：TPM 佈建需寫入 /opt/hiba/tpm 與 apt 安裝，皆需 root
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        log_fn("  WARN  未以 root 執行 — 跳過 TPM 機器綁定（授權將為浮動授權）")
        log_fn("  INFO  若需 TPM 機器綁定，請以 sudo 重新執行安裝精靈：")
        log_fn("  INFO    sudo python3 install-wizard.py")
        log_fn("  INFO  或先在伺服器執行 sudo bash 01_tpm_full_setup.sh 再安裝")
        return

    # Install tpm2-tools if missing
    if not shutil.which("tpm2_createek"):
        log_fn("  INFO  tpm2-tools 未安裝，嘗試自動安裝 (apt-get)...")
        rc = _run_cmd(["apt-get", "install", "-y", "tpm2-tools"], sys_root)
        if rc != 0:
            log_fn("  WARN  tpm2-tools 安裝失敗（非致命）— 跳過 TPM 機器綁定設定")
            return
        log_fn("  OK  tpm2-tools 安裝完成")
    else:
        log_fn("  OK  tpm2-tools 已存在")

    # Check TPM device — fallback to swtpm if no hardware TPM found
    has_hw_tpm = Path("/dev/tpmrm0").exists() or Path("/dev/tpm0").exists()
    if not has_hw_tpm:
        log_fn("  INFO  未偵測到硬體 TPM (/dev/tpmrm0, /dev/tpm0) — 嘗試安裝 swtpm 軟體 vTPM...")
        if not _setup_swtpm_linux(log_fn, sys_root):
            log_fn("  WARN  swtpm 設定失敗 — 跳過 TPM 機器綁定設定（授權將為浮動授權）")
            return
        log_fn("  OK   swtpm vTPM 就緒，繼續匯出公鑰...")
    else:
        log_fn("  OK   硬體 TPM 已偵測到")
        # Add service user to tss group (硬體 TPM 才需要 — swtpm 使用 TCP 不需要此 group)
        if os.getuid() == 0:
            service_user = os.environ.get("SUDO_USER", "")
            if not service_user:
                env_path = sys_root / ".env"
                if env_path.exists():
                    for line in env_path.read_text().splitlines():
                        if line.startswith("SERVICE_USER="):
                            service_user = line.split("=", 1)[1].strip("'\"")
                            break
            if service_user:
                rc = _run_cmd(["usermod", "-aG", "tss", service_user], sys_root)
                log_fn(f"  {'OK' if rc == 0 else 'WARN'}  usermod -aG tss {service_user}" + ("" if rc == 0 else "（失敗，非致命）"))

    # Export signing public key and save machine-pubkey.pem
    probe = _probe_tpm_signing_pubkey()
    if probe["pubkey_pem"]:
        pubkey_file = sys_root / "machine-pubkey.pem"
        pubkey_file.write_text(probe["pubkey_pem"] + "\n", encoding="utf-8")
        log_fn(f"  OK  TPM 公鑰已儲存 → {pubkey_file.name}")
        log_fn(f"  INFO  來源: {probe['source']}")
        log_fn("  INFO  請將 machine-pubkey.pem 提供給授權方以取得機器綁定授權")
    else:
        log_fn("  WARN  無法取得 TPM 公鑰（handle 0x81000001 尚未佈建，請執行 01_tpm_full_setup.sh）")


def _setup_swtpm_linux(log_fn, sys_root: Path) -> bool:
    """
    安裝 swtpm 套件並執行持久化 swtpm 初始化腳本。
    呼叫時機：_setup_tpm_linux() 偵測到沒有硬體 TPM (/dev/tpmrm0, /dev/tpm0) 時。
    成功後設定 TPM2TOOLS_TCTI 環境變數，使 _probe_tpm_fingerprint() 透過 swtpm 取得指紋。
    回傳 True 表示 swtpm 成功啟動且 TCTI 已設定。
    """
    import shutil

    # 安裝 swtpm + swtpm-tools（若未安裝）
    pkgs_needed: list[str] = []
    if not shutil.which("swtpm"):
        pkgs_needed.append("swtpm")
    if not shutil.which("swtpm_setup"):
        pkgs_needed.append("swtpm-tools")

    if pkgs_needed:
        log_fn(f"  INFO  安裝 swtpm 套件：{' '.join(pkgs_needed)}")
        rc = _run_cmd(["apt-get", "install", "-y"] + pkgs_needed, sys_root)
        if rc != 0:
            log_fn("  WARN  swtpm 套件安裝失敗（apt-get 錯誤）")
            return False
        log_fn("  OK   swtpm 套件安裝完成")
    else:
        log_fn("  OK   swtpm 已安裝")

    # 將內嵌腳本寫入暫存檔並執行
    script_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, encoding="utf-8"
        ) as f:
            f.write(_SWTPM_SETUP_SCRIPT)
            script_path = f.name

        os.chmod(script_path, 0o755)
        log_fn("  INFO  執行 swtpm 持久化初始化（約 10–30 秒）...")
        rc = _run_cmd(["bash", script_path], sys_root)
        if rc != 0:
            log_fn(f"  WARN  swtpm 初始化腳本結束碼 {rc}（可能部分步驟失敗）")
            return False
    finally:
        if script_path and Path(script_path).exists():
            try:
                os.unlink(script_path)
            except OSError:
                pass

    # 設定 TCTI 環境變數，使後續 tpm2_createek 透過 swtpm 運作
    tcti = "swtpm:host=127.0.0.1,port=2321"
    os.environ["TPM2TOOLS_TCTI"] = tcti
    log_fn(f"  OK   TPM2TOOLS_TCTI={tcti}")
    log_fn("  OK   swtpm vTPM 持久化完成（/opt/hiba/tpm/swtpm-state）")
    log_fn("  INFO  重開機後 swtpm 由 systemd 自動啟動，指紋不變")
    return True


def _venv_bin(sys_root: Path, name: str) -> Path:
    if platform.system() == "Windows":
        return sys_root / ".venv" / "Scripts" / (name + ".exe")
    return sys_root / ".venv" / "bin" / name


def _fs_supports_symlinks(d: Path) -> bool:
    """偵測目錄所在檔案系統是否支援 symlink（VirtualBox 共享資料夾 vboxsf 不支援）。"""
    if platform.system() == "Windows":
        return True
    test_target = d / ".__symlink_probe_target"
    test_link = d / ".__symlink_probe_link"
    try:
        test_target.write_text("x", encoding="utf-8")
        if test_link.is_symlink() or test_link.exists():
            test_link.unlink()
        os.symlink(test_target.name, test_link)
        return test_link.is_symlink()
    except (OSError, NotImplementedError):
        return False
    finally:
        for p in (test_link, test_target):
            try:
                if p.is_symlink() or p.exists():
                    p.unlink()
            except OSError:
                pass


def _create_venv(sys_root: Path, log_fn) -> int:
    """
    建立 .venv。在不支援 symlink 的檔案系統（如 VirtualBox 共享資料夾）上，
    Python venv 預設會嘗試建立 lib64 -> lib symlink 而失敗，故：
      - 改用 --copies（bin/python 用複製而非 symlink）
      - 預先建立 lib64 為真實目錄，讓 venv 跳過 symlink 建立
    """
    import shutil

    venv_path = sys_root / ".venv"
    # 手動清空（取代 --clear，因 --clear 會刪掉預建的 lib64）
    if venv_path.exists():
        shutil.rmtree(venv_path, ignore_errors=True)

    cmd = [sys.executable, "-m", "venv"]
    if not _fs_supports_symlinks(sys_root):
        log_fn("  INFO  偵測到檔案系統不支援 symlink（如 VirtualBox 共享資料夾 /media/sf_*）")
        log_fn("  INFO  改用 --copies 模式並預建 lib64 目錄以繞過 symlink 限制")
        try:
            (venv_path / "lib64").mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log_fn(f"  WARN  預建 lib64 失敗：{e}")
        cmd.append("--copies")
    cmd.append(str(venv_path))
    return _run_cmd(cmd, sys_root)


def _write_env(sys_root: Path, values: dict) -> None:
    lines: list[str] = []
    for k, v in values.items():
        safe = str(v).replace("\\", "\\\\").replace("'", "\\'")
        lines.append(f"{k}='{safe}'")
    content = "\n".join(lines) + "\n"
    # 寫到 system/.env（供 docker-compose / 參考）與 system/backend/.env
    # （後端常從 backend/ 啟動，pydantic 依 cwd 找 .env）。雙寫確保兩種啟動方式皆可讀到。
    (sys_root / ".env").write_text(content, encoding="utf-8")
    backend_dir = sys_root / "backend"
    if backend_dir.is_dir():
        (backend_dir / ".env").write_text(content, encoding="utf-8")


def _run_cmd(cmd: list[str], cwd: Path) -> int:
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        with _lock:
            _install_state["log"].append(line.rstrip())
    proc.wait()
    return proc.returncode


def _install_worker(env: dict, sys_root: Path) -> None:
    with _lock:
        _install_state.update({"running": True, "log": [], "success": None, "step_idx": -1})

    def log(msg: str) -> None:
        with _lock:
            _install_state["log"].append(msg)

    def step(i: int, label: str) -> None:
        log(f"\n{'='*60}\n  步驟 {i+1}: {label}\n{'='*60}")
        with _lock:
            _install_state["step_idx"] = i

    try:
        # Step 0: Write .env
        step(0, "寫入設定檔 (.env)")
        _write_env(sys_root, env)
        log(f"  OK  {sys_root / '.env'}")

        # Step 0.5: TPM setup (Linux only, best-effort — does not abort on failure)
        if platform.system() == "Linux":
            log(f"\n{'='*60}\n  TPM 2.0 機器公鑰設定\n{'='*60}")
            _setup_tpm_linux(log, sys_root)

        # Step 1: Create venv
        step(1, "建立 Python 虛擬環境")
        rc = _create_venv(sys_root, log)
        if rc != 0:
            raise RuntimeError(
                f"venv 建立失敗 (exit {rc})。"
                f"若部署於 VirtualBox 共享資料夾，建議先複製到原生路徑（如 ~/form-system）再安裝。"
            )
        log("  OK  .venv 建立完成")

        # Step 2: pip install
        step(2, "安裝後端相依套件 (可能需要數分鐘)")
        pip = _venv_bin(sys_root, "pip")
        _run_cmd([str(pip), "install", "-q", "--upgrade", "pip"], sys_root)
        req = sys_root / "backend" / "requirements.txt"
        rc = _run_cmd([str(pip), "install", "-r", str(req)], sys_root)
        if rc != 0:
            raise RuntimeError(f"pip install 失敗 (exit {rc})")
        log("  OK  相依套件安裝完成")

        # Step 3: DB migration
        step(3, "資料庫初始化")
        python = _venv_bin(sys_root, "python")
        bd = sys_root / "backend"
        if (bd / "alembic.ini").exists():
            rc = _run_cmd([str(python), "-m", "alembic", "upgrade", "head"], bd)
        elif (bd / "app" / "core" / "generated_db_bootstrap.py").exists():
            rc = _run_cmd([str(python), "-m", "app.core.generated_db_bootstrap"], bd)
        else:
            log("  SKIP  找不到 migration 工具，略過")
            rc = 0
        if rc != 0:
            raise RuntimeError(f"資料庫初始化失敗 (exit {rc})")
        log("  OK  資料庫就緒")

        # Done
        log("\n" + "="*60)
        log("  安裝完成！")
        log("="*60)
        log(f"\n  系統目錄  : {sys_root}")
        log(f"  啟動指令  : {python} -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
        log(f"  工作目錄  : {bd}")
        with _lock:
            _install_state["success"] = True

    except Exception as exc:  # noqa: BLE001
        with _lock:
            _install_state["log"].append(f"\n[錯誤] {exc}")
            _install_state["success"] = False
    finally:
        with _lock:
            _install_state["running"] = False


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        pass  # silence default access log

    def _send_json(self, obj: object, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, ct: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path == "/" or path == "/index.html":
            data = _HTML.encode("utf-8")
            self._send_bytes(data, "text/html; charset=utf-8")

        elif path == "/api/recipe":
            self._send_json(_read_recipe())

        elif path == "/api/prereqs":
            checks = []
            for tool in ("python3", "pip3"):
                try:
                    out = subprocess.check_output(
                        [tool, "--version"], stderr=subprocess.STDOUT, text=True
                    ).strip()
                    checks.append({"tool": tool, "ok": True, "version": out})
                except Exception:
                    checks.append({"tool": tool, "ok": False, "version": "not found"})
            self._send_json({"checks": checks})

        elif path == "/api/generate-key":
            self._send_json({"key": _generate_secret()})

        elif path == "/api/sys-root":
            qs = self.path.partition("?")[2]
            custom_path: str | None = None
            for part in qs.split("&"):
                if part.startswith("path="):
                    from urllib.parse import unquote_plus
                    custom_path = unquote_plus(part.split("=", 1)[1])
            if custom_path:
                p = Path(custom_path)
                found = (p / "backend" / "requirements.txt").exists()
                self._send_json({"found": found, "path": str(p.resolve()) if found else str(p)})
            else:
                sr = _find_sys_root()
                self._send_json({"found": sr is not None, "path": str(sr) if sr else None})

        elif path == "/api/machine-pubkey":
            probe = _probe_tpm_signing_pubkey()
            self._send_json({
                "found": probe["pubkey_pem"] is not None,
                "pubkey_pem": probe["pubkey_pem"],
                "source": probe["source"],
            })

        elif path == "/api/check-license":
            import hashlib as _hl, json as _json
            sr = _find_sys_root()
            if not sr:
                self._send_json({"valid": False, "reason": "sys_root_not_found"})
                return
            lic_path = sr / "license.lic"
            if not lic_path.exists():
                self._send_json({"valid": False, "reason": "no_license_file"})
                return
            try:
                lic_data = _json.loads(lic_path.read_text("utf-8"))
                payload = _json.loads(lic_data["payload"])
                # Expiry check
                expires_at = payload.get("expiresAt", "")
                if expires_at:
                    from datetime import datetime, timezone
                    if datetime.now(timezone.utc) > datetime.fromisoformat(expires_at.replace("Z", "+00:00")):
                        self._send_json({"valid": False, "reason": "expired", "expires_at": expires_at})
                        return
                # TPM machine binding via challenge-response
                expected_pubkey = payload.get("machinePublicKey")
                machine_bound = bool(expected_pubkey)
                if expected_pubkey:
                    import os as _os
                    nonce = _os.urandom(32)
                    sig = _wizard_tpm_sign_nonce(nonce)
                    if sig is None:
                        self._send_json({"valid": False, "reason": "tpm_unavailable",
                                         "detail": f"TPM handle {_TPM_SIGNING_HANDLE} not responding"})
                        return
                    try:
                        from cryptography.hazmat.primitives import hashes, serialization
                        from cryptography.hazmat.primitives.asymmetric import padding as _pad
                        pub = serialization.load_pem_public_key(expected_pubkey.encode())
                        pub.verify(sig, nonce, _pad.PKCS1v15(), hashes.SHA256())
                    except Exception as _ve:
                        self._send_json({"valid": False, "reason": "tpm_mismatch",
                                         "detail": "challenge-response failed — different TPM"})
                        return
                licensee = payload.get("licensee", {})
                self._send_json({"valid": True, "licensee": licensee, "expires_at": expires_at,
                                 "machine_bound": machine_bound,
                                 "binding_method": "tpm2-challenge-response" if machine_bound else "none"})
            except Exception as exc:
                self._send_json({"valid": False, "reason": str(exc)})

        # /api/check-machine-id removed — replaced by TPM challenge-response in /api/check-license

        elif path == "/api/ls":
            from urllib.parse import unquote_plus
            qs = self.path.partition("?")[2]
            raw_path: str | None = None
            for part in qs.split("&"):
                if part.startswith("path="):
                    raw_path = unquote_plus(part.split("=", 1)[1])
            target = Path(raw_path) if raw_path else Path.home()
            try:
                dirs = sorted(
                    p.name for p in target.iterdir()
                    if p.is_dir() and not p.name.startswith(".")
                )
                parent = str(target.parent) if target.parent != target else None
                self._send_json({"path": str(target.resolve()), "dirs": dirs, "parent": parent})
            except Exception as e:
                self._send_json({"path": str(target), "dirs": [], "parent": None, "error": str(e)})

        elif path == "/api/log":
            qs = self.path.partition("?")[2]
            offset = 0
            for part in qs.split("&"):
                if part.startswith("offset="):
                    offset = int(part.split("=", 1)[1])
            with _lock:
                lines = _install_state["log"][offset:]
                snap = {
                    "running": _install_state["running"],
                    "step_idx": _install_state["step_idx"],
                    "success": _install_state["success"],
                }
            self._send_json({"lines": lines, "offset": offset + len(lines), **snap})

        else:
            self._send_bytes(b"Not found", "text/plain", 404)

    def do_POST(self) -> None:
        path = self.path
        body = self._read_body()

        if path == "/api/test-db":
            host = body.get("host", "localhost")
            port = int(body.get("port", 5432))
            try:
                s = socket.create_connection((host, port), timeout=3)
                s.close()
                self._send_json({"ok": True, "msg": f"已連線到 {host}:{port}"})
            except Exception as e:
                self._send_json({"ok": False, "msg": str(e)})

        elif path == "/api/install":
            with _lock:
                if _install_state["running"]:
                    self._send_json({"ok": False, "msg": "安裝已在執行中"})
                    return
            custom_root = body.get("sysRoot")
            if custom_root:
                sys_root = Path(custom_root)
                if not (sys_root / "backend" / "requirements.txt").exists():
                    self._send_json({"ok": False, "msg": f"無效的系統目錄：{custom_root}"})
                    return
            else:
                sys_root = _find_sys_root()
            if sys_root is None:
                self._send_json({"ok": False, "msg": "找不到 system 目錄"})
                return
            env = body.get("env", {})
            threading.Thread(target=_install_worker, args=(env, sys_root), daemon=True).start()
            self._send_json({"ok": True})

        elif path == "/api/heartbeat":
            global _last_heartbeat
            _last_heartbeat = time.time()
            self._send_json({"ok": True})

        elif path == "/api/shutdown":
            self._send_json({"ok": True})
            def _stop() -> None:
                time.sleep(0.3)
                _server_ref[0].shutdown()
            threading.Thread(target=_stop, daemon=True).start()

        else:
            self._send_bytes(b"Not found", "text/plain", 404)


_server_ref: list = [None]

# ── Embedded HTML/CSS/JS ──────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Form System 安裝精靈</title>
<style>
:root {
  --primary: #2563eb;
  --primary-h: #1d4ed8;
  --success: #16a34a;
  --error:   #dc2626;
  --warn:    #d97706;
  --bg:      #f1f5f9;
  --card:    #ffffff;
  --border:  #e2e8f0;
  --text:    #1e293b;
  --muted:   #64748b;
  --radius:  10px;
  --shadow:  0 1px 4px rgba(0,0,0,.08), 0 4px 16px rgba(0,0,0,.06);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui,-apple-system,'Segoe UI',sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  padding-bottom: 40px;
}
a { color: var(--primary); }

/* ── Header ──────────────────────────────────────────── */
.hdr {
  background: var(--primary);
  color: #fff;
  padding: 14px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.hdr-icon { font-size: 24px; }
.hdr-title { font-size: 18px; font-weight: 600; }
.hdr-recipe { font-size: 13px; opacity: .75; margin-left: auto; }

/* ── Container ────────────────────────────────────────── */
.wrap { max-width: 700px; margin: 0 auto; padding: 0 16px; }

/* ── Step indicator ───────────────────────────────────── */
.steps {
  display: flex;
  align-items: center;
  gap: 0;
  margin: 28px 0 0;
}
.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  position: relative;
}
.step-item:not(:first-child)::before {
  content: '';
  position: absolute;
  left: -50%;
  right: 50%;
  top: 16px;
  height: 2px;
  background: var(--border);
  transition: background .3s;
}
.step-item.done::before, .step-item.active::before { background: var(--primary); }
.step-circle {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--border);
  color: var(--muted);
  font-size: 13px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  position: relative; z-index: 1;
  transition: background .3s, color .3s;
}
.step-item.active .step-circle { background: var(--primary); color: #fff; }
.step-item.done  .step-circle { background: var(--success); color: #fff; }
.step-item.done  .step-circle::after { content: '✓'; }
.step-item.done  .step-circle span { display: none; }
.step-label { font-size: 11px; color: var(--muted); margin-top: 4px; text-align: center; white-space: nowrap; }
.step-item.active .step-label { color: var(--primary); font-weight: 600; }

/* ── Card ─────────────────────────────────────────────── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 32px;
  margin-top: 20px;
}
.card-title { font-size: 20px; font-weight: 700; margin-bottom: 6px; }
.card-sub   { color: var(--muted); font-size: 14px; margin-bottom: 24px; }

/* ── Form elements ───────────────────────────────────── */
.field { margin-bottom: 16px; }
.field label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 5px; }
.field .hint  { font-size: 12px; color: var(--muted); margin-top: 3px; }
.field input {
  width: 100%; padding: 9px 12px;
  border: 1px solid var(--border); border-radius: 6px;
  font-size: 14px; color: var(--text);
  transition: border-color .2s, box-shadow .2s;
  outline: none;
}
.field input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37,99,235,.15);
}
.field input.err { border-color: var(--error); }
.row2 { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
.field-err { font-size: 12px; color: var(--error); margin-top: 3px; display: none; }
.field-err.show { display: block; }

/* ── Input with button ────────────────────────────────── */
.input-btn-row { display: flex; gap: 8px; }
.input-btn-row input { flex: 1; }

/* ── Buttons ─────────────────────────────────────────── */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 9px 20px; border-radius: 6px; font-size: 14px; font-weight: 600;
  cursor: pointer; border: none; transition: background .2s, opacity .2s;
}
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--primary); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--primary-h); }
.btn-secondary { background: var(--border); color: var(--text); }
.btn-secondary:hover:not(:disabled) { background: #cbd5e1; }
.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn-outline:hover:not(:disabled) { background: var(--bg); }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.btn-success { background: var(--success); color: #fff; }
.nav-row { display: flex; justify-content: space-between; align-items: center; margin-top: 28px; }

/* ── Status badges ───────────────────────────────────── */
.badge {
  display: inline-block; padding: 3px 10px; border-radius: 100px;
  font-size: 12px; font-weight: 600;
}
.badge-blue  { background: #dbeafe; color: #1d4ed8; }
.badge-green { background: #dcfce7; color: #15803d; }
.badge-gray  { background: #f1f5f9; color: var(--muted); }

/* ── Prereq checklist ────────────────────────────────── */
.check-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 24px; }
.check-item {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 16px; border: 1px solid var(--border);
  border-radius: 8px; transition: border-color .2s, background .2s;
}
.check-item.loading { background: var(--bg); }
.check-item.ok  { border-color: #86efac; background: #f0fdf4; }
.check-item.err { border-color: #fca5a5; background: #fef2f2; }
.check-icon { font-size: 22px; flex-shrink: 0; width: 28px; text-align: center; }
.check-item.ok  .check-icon { color: var(--success); }
.check-item.err .check-icon { color: var(--error); }
.check-name { font-size: 14px; font-weight: 600; }
.check-ver  { font-size: 12px; color: var(--muted); margin-top: 2px; }

/* ── DB test status ──────────────────────────────────── */
.db-status { font-size: 13px; margin-top: 8px; padding: 8px 12px; border-radius: 6px; display: none; }
.db-status.ok  { background: #dcfce7; color: #15803d; display: block; }
.db-status.err { background: #fee2e2; color: #991b1b; display: block; }

/* ── Review table ────────────────────────────────────── */
.review-table { width: 100%; border-collapse: collapse; }
.review-table tr td { padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
.review-table tr td:first-child { color: var(--muted); width: 40%; font-weight: 500; }
.review-table tr:last-child td { border-bottom: none; }

/* ── Install progress steps ──────────────────────────── */
.inst-steps { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.inst-step {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: 100px;
  font-size: 13px; font-weight: 600;
  background: var(--border); color: var(--muted);
  transition: background .3s, color .3s;
}
.inst-step.active { background: #dbeafe; color: var(--primary); }
.inst-step.done   { background: #dcfce7; color: var(--success); }
.inst-step.err    { background: #fee2e2; color: var(--error);   }
.spin { display: inline-block; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Log box ─────────────────────────────────────────── */
.log-box {
  background: #0f172a; color: #94a3b8;
  font-family: 'Cascadia Code','Consolas',monospace;
  font-size: 12px; line-height: 1.6;
  padding: 16px; border-radius: 8px;
  height: 280px; overflow-y: auto;
  white-space: pre-wrap; word-break: break-all;
}
.log-box .log-ok   { color: #4ade80; }
.log-box .log-err  { color: #f87171; }
.log-box .log-head { color: #60a5fa; font-weight: bold; }

/* ── Done panel ──────────────────────────────────────── */
.done-box { padding: 20px; border-radius: 8px; margin-bottom: 20px; }
.done-box.ok  { background: #dcfce7; border: 1px solid #86efac; }
.done-box.err { background: #fee2e2; border: 1px solid #fca5a5; }
.done-box .done-icon { font-size: 36px; margin-bottom: 8px; }
.done-box h3  { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
.done-box p   { font-size: 14px; color: var(--muted); }
.cmd-box { background: #0f172a; color: #e2e8f0; font-family: monospace; font-size: 13px; padding: 14px 16px; border-radius: 8px; margin-top: 16px; }

/* ── Welcome info grid ───────────────────────────────── */
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; }
.info-cell { padding: 14px 16px; background: var(--bg); border-radius: 8px; }
.info-cell .ic-label { font-size: 11px; color: var(--muted); text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }
.info-cell .ic-val   { font-size: 14px; font-weight: 700; }
.kit-list { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
</style>
</head>
<body>

<div class="hdr">
  <span class="hdr-icon">&#9881;</span>
  <span class="hdr-title">Form System 安裝精靈</span>
  <span class="hdr-recipe" id="hdr-recipe">載入中...</span>
</div>

<div class="wrap">

  <!-- Step indicator -->
  <div class="steps" id="steps-bar">
    <div class="step-item" data-step="0"><div class="step-circle"><span>1</span></div><div class="step-label">歡迎</div></div>
    <div class="step-item" data-step="1"><div class="step-circle"><span>2</span></div><div class="step-label">所需應用</div></div>
    <div class="step-item" data-step="2"><div class="step-circle"><span>3</span></div><div class="step-label">資料庫</div></div>
    <div class="step-item" data-step="3"><div class="step-circle"><span>4</span></div><div class="step-label">管理者</div></div>
    <div class="step-item" data-step="4"><div class="step-circle"><span>5</span></div><div class="step-label">安全設定</div></div>
    <div class="step-item" data-step="5"><div class="step-circle"><span>6</span></div><div class="step-label">確認</div></div>
    <div class="step-item" data-step="6"><div class="step-circle"><span>7</span></div><div class="step-label">安裝</div></div>
  </div>

  <!-- ── STEP 0: Welcome ─────────────────────────────── -->
  <div class="card" id="step-0">
    <div class="card-title">歡迎使用 Form System 安裝精靈</div>
    <div class="card-sub">此精靈將引導您完成系統安裝，約需 5–15 分鐘。</div>
    <div class="info-grid">
      <div class="info-cell"><div class="ic-label">Recipe</div><div class="ic-val" id="info-recipe">—</div></div>
      <div class="info-cell"><div class="ic-label">資料庫</div><div class="ic-val" id="info-db">—</div></div>
      <div class="info-cell"><div class="ic-label">Kit 數量</div><div class="ic-val" id="info-kits">—</div></div>
    </div>
    <div id="kits-panel" style="margin-bottom:20px">
      <div style="font-size:13px;color:var(--muted);margin-bottom:8px;font-weight:600">已選 Kits</div>
      <div class="kit-list" id="kit-list"></div>
    </div>
    <div class="field" style="margin-bottom:20px">
      <label>系統目錄</label>
      <div class="input-btn-row">
        <input id="info-sysroot" type="text" style="font-family:monospace;font-size:12px" placeholder="自動偵測中…">
        <button class="btn btn-outline btn-sm" onclick="openDirBrowser()" title="瀏覽資料夾">…</button>
        <button class="btn btn-outline btn-sm" onclick="verifySysRoot()">驗證</button>
      </div>
      <div id="sysroot-status" style="font-size:12px;margin-top:5px;display:none"></div>
    </div>
    <div class="field" style="margin-bottom:20px" id="machine-id-panel" style="display:none">
      <label>本機 TPM 公鑰 <span id="fp-source-badge" class="badge badge-green" style="margin-left:8px;font-size:11px;vertical-align:middle">TPM 硬體綁定</span></label>
      <textarea id="machine-id-display" readonly rows="5" style="font-family:monospace;font-size:11px;background:#f5f5f5;width:100%;resize:vertical;border:1px solid #e5e7eb;border-radius:6px;padding:8px;box-sizing:border-box"></textarea>
      <div style="display:flex;gap:8px;margin-top:6px">
        <button class="btn btn-outline btn-sm" onclick="copyMachinePubkey()">複製公鑰</button>
        <button class="btn btn-outline btn-sm" onclick="downloadMachinePubkey()">下載 .pem</button>
      </div>
      <div class="hint">若授權需要機器綁定，請將此 RSA 公鑰提供給授權方（可複製或下載 .pem）。<br>授權方以此公鑰簽發 license.lic，系統啟動時透過 TPM 挑戰-回應驗證綁定。</div>
    </div>
    <div class="nav-row">
      <span></span>
      <button class="btn btn-primary" id="btn-welcome-next" onclick="goNext()">開始安裝 &rarr;</button>
    </div>
  </div>

  <!-- ── Dir browser modal ──────────────────────────────── -->
  <div id="dir-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1000;align-items:center;justify-content:center">
    <div style="background:#fff;border-radius:10px;padding:24px;width:520px;max-width:95vw;max-height:80vh;display:flex;flex-direction:column;gap:12px;box-shadow:0 8px 32px rgba(0,0,0,.2)">
      <div style="font-weight:600;font-size:15px">選擇系統目錄</div>
      <div style="font-family:monospace;font-size:12px;background:#f5f5f5;padding:6px 10px;border-radius:4px;word-break:break-all" id="dir-cur-path">—</div>
      <div style="overflow-y:auto;flex:1;border:1px solid #e5e7eb;border-radius:6px;max-height:320px" id="dir-list"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button class="btn btn-secondary btn-sm" onclick="closeDirBrowser()">取消</button>
        <button class="btn btn-primary btn-sm" id="dir-select-btn" onclick="selectCurrentDir()">選擇此資料夾</button>
      </div>
    </div>
  </div>

  <!-- ── STEP 1: Prerequisites ─────────────────────────── -->
  <div class="card" id="step-1" style="display:none">
    <div class="card-title">所需應用程式</div>
    <div class="card-sub">安裝前請確認以下工具已安裝於目標主機。</div>
    <div class="check-list" id="prereq-list">
      <div class="check-item loading">
        <div class="check-icon">&#9711;</div>
        <div><div class="check-name">檢查中…</div></div>
      </div>
    </div>
    <div id="prereq-warn" style="display:none;background:#fee2e2;border:1px solid #fca5a5;border-radius:8px;padding:12px 16px;font-size:13px;color:#991b1b">
      ⚠ 有工具尚未安裝，請安裝後點擊「重新檢查」再繼續。
    </div>
    <div class="nav-row">
      <button class="btn btn-secondary" onclick="goStep(0)">&larr; 上一步</button>
      <span>
        <button class="btn btn-outline btn-sm" onclick="runPrereqs()" style="margin-right:8px">重新檢查</button>
        <button class="btn btn-primary" id="btn-prereq-next" disabled onclick="goNext()">下一步 &rarr;</button>
      </span>
    </div>
  </div>

  <!-- ── STEP 2: Database ───────────────────────────────── -->
  <div class="card" id="step-2" style="display:none">
    <div class="card-title">資料庫連線設定</div>
    <div class="card-sub">支援 PostgreSQL（生產環境）。若未設定 DATABASE_URL，系統自動使用 SQLite（僅限本機測試）。</div>
    <div class="row2">
      <div class="field">
        <label>資料庫主機</label>
        <input id="db-host" type="text" value="localhost" oninput="clearDbStatus()">
      </div>
      <div class="field">
        <label>連接埠</label>
        <input id="db-port" type="number" value="5432" oninput="clearDbStatus()">
      </div>
    </div>
    <div class="row2">
      <div class="field">
        <label>資料庫名稱</label>
        <input id="db-name" type="text" value="form_system">
      </div>
      <div class="field">
        <label>使用者名稱</label>
        <input id="db-user" type="text" value="form_system">
      </div>
    </div>
    <div class="field">
      <label>資料庫密碼</label>
      <input id="db-pass" type="password" placeholder="輸入資料庫密碼">
      <div class="hint">留空將略過 PostgreSQL，改用 SQLite（DATABASE_URL 留空）</div>
    </div>
    <button class="btn btn-outline btn-sm" onclick="testDb()">&#128268; 測試連線</button>
    <div class="db-status" id="db-status"></div>
    <div class="nav-row">
      <button class="btn btn-secondary" onclick="goStep(1)">&larr; 上一步</button>
      <button class="btn btn-primary" onclick="goNext()">下一步 &rarr;</button>
    </div>
  </div>

  <!-- ── STEP 3: Manager ───────────────────────────────── -->
  <div class="card" id="step-3" style="display:none">
    <div class="card-title">管理者帳號設定</div>
    <div class="card-sub">設定系統初始 Manager 帳號，首次登入後將要求修改密碼。</div>
    <div class="field">
      <label>帳號名稱</label>
      <input id="mgr-user" type="text" value="manager">
      <div class="field-err" id="err-mgr-user">帳號名稱不得為空</div>
    </div>
    <div class="field">
      <label>密碼（至少 8 碼）</label>
      <input id="mgr-pass" type="password" oninput="checkPassMatch()">
      <div class="field-err" id="err-mgr-pass">密碼至少 8 個字元</div>
    </div>
    <div class="field">
      <label>確認密碼</label>
      <input id="mgr-pass2" type="password" oninput="checkPassMatch()">
      <div class="field-err" id="err-mgr-pass2">兩次密碼不一致</div>
    </div>
    <div class="nav-row">
      <button class="btn btn-secondary" onclick="goStep(2)">&larr; 上一步</button>
      <button class="btn btn-primary" id="btn-mgr-next" onclick="validateManager()">下一步 &rarr;</button>
    </div>
  </div>

  <!-- ── STEP 4: Security ──────────────────────────────── -->
  <div class="card" id="step-4" style="display:none">
    <div class="card-title">安全金鑰設定</div>
    <div class="card-sub">SECRET_KEY 用於 JWT / session 加密，請使用隨機產生的強金鑰。</div>
    <div class="field">
      <label>SECRET_KEY</label>
      <div class="input-btn-row">
        <input id="secret-key" type="text" placeholder="點擊「產生」自動生成...">
        <button class="btn btn-outline btn-sm" onclick="generateKey()">&#128273; 產生</button>
      </div>
      <div class="field-err" id="err-secret-key">SECRET_KEY 不得為空</div>
    </div>
    <div class="field">
      <label>CORS_ORIGINS</label>
      <input id="cors-origins" type="text" value="http://localhost:5173,http://localhost:3000">
      <div class="hint">多個來源用逗號分隔。生產環境應填寫實際網域。</div>
    </div>
    <div class="nav-row">
      <button class="btn btn-secondary" onclick="goStep(3)">&larr; 上一步</button>
      <button class="btn btn-primary" onclick="validateSecurity()">下一步 &rarr;</button>
    </div>
  </div>

  <!-- ── STEP 5: Review ───────────────────────────────── -->
  <div class="card" id="step-5" style="display:none">
    <div class="card-title">確認設定</div>
    <div class="card-sub">請確認以下設定正確，點擊「開始安裝」後將寫入 .env 並執行安裝。</div>
    <table class="review-table" id="review-table"></table>
    <div id="license-check-result" style="display:none;margin:16px 0;padding:12px 14px;border-radius:6px;font-size:13px;"></div>
    <div class="nav-row">
      <button class="btn btn-secondary" onclick="goStep(4)">&larr; 上一步</button>
      <button class="btn btn-primary" id="btn-start-install" onclick="startInstall()">&#9658; 開始安裝</button>
    </div>
  </div>

  <!-- ── STEP 6: Install ──────────────────────────────── -->
  <div class="card" id="step-6" style="display:none">
    <div class="card-title">安裝中...</div>
    <div class="card-sub">請勿關閉此視窗，安裝過程約需 3–10 分鐘。</div>
    <div class="inst-steps" id="inst-steps">
      <div class="inst-step" id="ist-0">&#9679; 寫入設定</div>
      <div class="inst-step" id="ist-1">&#9679; 建立環境</div>
      <div class="inst-step" id="ist-2">&#9679; 安裝套件</div>
      <div class="inst-step" id="ist-3">&#9679; 資料庫</div>
    </div>
    <div class="log-box" id="log-box">等待安裝啟動...</div>
  </div>

  <!-- ── STEP 7: Done ─────────────────────────────────── -->
  <div class="card" id="step-7" style="display:none">
    <div id="done-success" style="display:none">
      <div class="done-box ok">
        <div class="done-icon">&#10003;</div>
        <h3>安裝成功！</h3>
        <p>Form System 已成功安裝，請使用以下指令啟動後端服務。</p>
      </div>
      <div style="font-size:14px;font-weight:600;margin-bottom:8px">啟動後端：</div>
      <div class="cmd-box" id="start-cmd"></div>
      <div style="margin-top:20px;font-size:14px;color:var(--muted)">
        後端啟動後，前端位於 <code>system/frontend/dist/</code>，透過 nginx 或 <code>npm run dev</code>（僅限測試）提供服務。
      </div>
    </div>
    <div id="done-error" style="display:none">
      <div class="done-box err">
        <div class="done-icon">&#10007;</div>
        <h3>安裝失敗</h3>
        <p>請查看上方安裝記錄了解詳細錯誤原因。</p>
      </div>
      <button class="btn btn-secondary" onclick="goStep(6)" style="margin-top:16px">&#9664; 查看安裝記錄</button>
    </div>
    <div style="margin-top:24px;text-align:right">
      <button class="btn btn-secondary" onclick="shutdownWizard()">&#10005; 關閉精靈</button>
    </div>
  </div>

</div><!-- /wrap -->

<script>
'use strict';

// ── State ────────────────────────────────────────────────────────────────────
const S = {
  currentStep: 0,
  prereqOk: false,
  recipe: {},
  sysRoot: null,
  logOffset: 0,
  pollTimer: null,
};

// ── TPM 公鑰顯示 ─────────────────────────────────────────────────────────────
async function loadMachineId() {
  try {
    const data = await fetch('/api/machine-pubkey').then(r => r.json());
    const panel = document.getElementById('machine-id-panel');
    const disp  = document.getElementById('machine-id-display');
    if (data.found && data.pubkey_pem) {
      disp.value = data.pubkey_pem;
      panel.style.display = 'block';
    }
  } catch (_) {}
}

function copyMachinePubkey() {
  const v = document.getElementById('machine-id-display')?.value;
  if (v) navigator.clipboard?.writeText(v).catch(() => {});
}

function downloadMachinePubkey() {
  const v = document.getElementById('machine-id-display')?.value;
  if (!v) return;
  const a = document.createElement('a');
  a.href = 'data:application/x-pem-file;charset=utf-8,' + encodeURIComponent(v);
  a.download = 'machine-pubkey.pem';
  a.click();
}

// ── License 驗證（TPM 挑戰-回應）────────────────────────────────────────────
async function checkMachineId() {
  const resultEl  = document.getElementById('license-check-result');
  const btnInstall = document.getElementById('btn-start-install');
  if (!resultEl) return;
  resultEl.style.display = 'block';
  resultEl.style.color = '';
  resultEl.style.background = '#f0f9ff';
  resultEl.style.border = '1px solid #bae6fd';
  resultEl.textContent = '授權驗證中…';
  try {
    const data = await fetch('/api/check-license').then(r => r.json());
    if (data.valid) {
      const bound = data.machine_bound
        ? ' | 機器綁定：TPM 挑戰-回應 通過'
        : ' | 浮動授權（未綁定機器）';
      resultEl.style.background = '#f0fdf4';
      resultEl.style.border = '1px solid #86efac';
      resultEl.style.color = '#166534';
      resultEl.textContent = '✓ 授權有效' + bound;
      if (btnInstall) btnInstall.disabled = false;
    } else if (data.reason === 'no_license_file') {
      resultEl.style.background = '#fffbeb';
      resultEl.style.border = '1px solid #fcd34d';
      resultEl.style.color = '#92400e';
      resultEl.textContent = '⚠ 未找到 license.lic，可繼續安裝（無授權限制）。';
      if (btnInstall) btnInstall.disabled = false;
    } else if (data.reason === 'tpm_mismatch') {
      resultEl.style.background = '#fef2f2';
      resultEl.style.border = '1px solid #fca5a5';
      resultEl.style.color = '#991b1b';
      resultEl.innerHTML = '<strong>TPM 機器綁定驗證失敗</strong><br>此授權僅限授權機器使用（TPM 挑戰-回應不符）。';
      if (btnInstall) btnInstall.disabled = true;
    } else if (data.reason === 'tpm_unavailable') {
      resultEl.style.background = '#fef2f2';
      resultEl.style.border = '1px solid #fca5a5';
      resultEl.style.color = '#991b1b';
      resultEl.innerHTML = '<strong>TPM 無法使用</strong><br>授權需要 TPM，但 handle 0x81000001 無回應。請先執行 01_tpm_full_setup.sh。';
      if (btnInstall) btnInstall.disabled = true;
    } else {
      resultEl.style.background = '#fef2f2';
      resultEl.style.border = '1px solid #fca5a5';
      resultEl.style.color = '#991b1b';
      resultEl.textContent = '授權驗證失敗：' + (data.reason || '未知錯誤');
      if (btnInstall) btnInstall.disabled = true;
    }
  } catch (_) {
    resultEl.style.background = '#fffbeb';
    resultEl.style.border = '1px solid #fcd34d';
    resultEl.style.color = '#92400e';
    resultEl.textContent = '⚠ 無法連線至本地授權服務，可繼續安裝。';
    if (btnInstall) btnInstall.disabled = false;
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  try {
    const [recipe, sr] = await Promise.all([
      fetch('/api/recipe').then(r => r.json()),
      fetch('/api/sys-root').then(r => r.json()),
    ]);
    S.recipe = recipe;
    S.sysRoot = sr.found ? sr.path : null;

    document.getElementById('hdr-recipe').textContent = recipe.name || 'unknown';
    document.getElementById('info-recipe').textContent = recipe.name || '—';
    document.getElementById('info-db').textContent = recipe.database?.engine || '—';
    const kits = recipe.enabledKits || [];
    document.getElementById('info-kits').textContent = kits.length + ' 個';
    document.getElementById('info-sysroot').value = sr.path || '';
    S.sysRoot = sr.found ? sr.path : null;
    if (sr.found) {
      setSysRootStatus(true, '已自動找到系統目錄');
    } else {
      setSysRootStatus(false, '找不到系統目錄，請手動輸入路徑後點擊「驗證」');
      document.getElementById('btn-welcome-next').disabled = true;
    }

    const kitList = document.getElementById('kit-list');
    kits.forEach(k => {
      const b = document.createElement('span');
      b.className = 'badge badge-blue';
      b.textContent = k;
      kitList.appendChild(b);
    });
    loadMachineId();
  } catch (e) {
    console.error('init error:', e);
  }
}

// ── Heartbeat — keeps watchdog alive while browser is open ───────────────────
setInterval(() => {
  fetch('/api/heartbeat', { method: 'POST' }).catch(() => {});
}, 5000);

// ── Sys-root editing ─────────────────────────────────────────────────────────
function setSysRootStatus(ok, msg) {
  const el = document.getElementById('sysroot-status');
  el.style.display = 'block';
  el.style.color = ok ? 'var(--success)' : 'var(--error)';
  el.textContent = (ok ? '✓ ' : '✗ ') + msg;
}

async function verifySysRoot() {
  const path = document.getElementById('info-sysroot').value.trim();
  if (!path) { setSysRootStatus(false, '請輸入路徑'); return; }
  const statusEl = document.getElementById('sysroot-status');
  statusEl.style.display = 'block';
  statusEl.style.color = 'var(--muted)';
  statusEl.textContent = '驗證中…';
  try {
    const data = await fetch('/api/sys-root?path=' + encodeURIComponent(path)).then(r => r.json());
    if (data.found) {
      S.sysRoot = data.path;
      document.getElementById('info-sysroot').value = data.path;
      setSysRootStatus(true, '路徑有效');
      document.getElementById('btn-welcome-next').disabled = false;
    } else {
      S.sysRoot = null;
      setSysRootStatus(false, '路徑無效：找不到 backend/requirements.txt');
      document.getElementById('btn-welcome-next').disabled = true;
    }
  } catch (e) {
    setSysRootStatus(false, '驗證失敗：' + e);
  }
}

// ── Dir browser ───────────────────────────────────────────────────────────────
let _dirBrowserPath = null;

async function openDirBrowser() {
  const modal = document.getElementById('dir-modal');
  modal.style.display = 'flex';
  const startPath = document.getElementById('info-sysroot').value.trim() || null;
  await _loadDir(startPath);
}

function closeDirBrowser() {
  document.getElementById('dir-modal').style.display = 'none';
}

async function _loadDir(path) {
  const url = '/api/ls' + (path ? '?path=' + encodeURIComponent(path) : '');
  const data = await fetch(url).then(r => r.json());
  _dirBrowserPath = data.path;
  document.getElementById('dir-cur-path').textContent = data.path;
  const list = document.getElementById('dir-list');
  let html = '';
  if (data.parent) {
    html += `<div onclick="_loadDir('${data.parent.replace(/'/g,"\\'")}');event.stopPropagation()" style="padding:8px 12px;cursor:pointer;border-bottom:1px solid #f0f0f0;color:var(--muted);font-size:13px">&#8593; 上層目錄</div>`;
  }
  if (data.dirs.length === 0) {
    html += '<div style="padding:12px;color:var(--muted);font-size:13px;text-align:center">（無子目錄）</div>';
  }
  for (const d of data.dirs) {
    const full = (data.path.endsWith('/') || data.path.endsWith('\\') ? data.path : data.path + '/') + d;
    html += `<div onclick="_loadDir('${full.replace(/'/g,"\\'")}');event.stopPropagation()" style="padding:8px 12px;cursor:pointer;border-bottom:1px solid #f0f0f0;font-size:13px;display:flex;align-items:center;gap:8px"><span style="color:#6b7280">&#128193;</span>${d}</div>`;
  }
  list.innerHTML = html;
}

async function selectCurrentDir() {
  if (!_dirBrowserPath) return;
  document.getElementById('info-sysroot').value = _dirBrowserPath;
  closeDirBrowser();
  await verifySysRoot();
}

async function shutdownWizard() {
  try { await fetch('/api/shutdown', { method: 'POST' }); } catch (_) {}
  window.close();
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goStep(n) {
  document.getElementById('step-' + S.currentStep).style.display = 'none';
  S.currentStep = n;
  document.getElementById('step-' + n).style.display = 'block';
  updateStepBar();
  window.scrollTo(0, 0);
  if (n === 1) runPrereqs();
  if (n === 5) { buildReview(); checkMachineId(); }
}

function goNext() { goStep(S.currentStep + 1); }

function updateStepBar() {
  document.querySelectorAll('#steps-bar .step-item').forEach((el, i) => {
    el.classList.remove('active', 'done');
    if (i < S.currentStep)     el.classList.add('done');
    else if (i === S.currentStep) el.classList.add('active');
  });
}

// ── Step 1: Prerequisites ─────────────────────────────────────────────────────
async function runPrereqs() {
  const list = document.getElementById('prereq-list');
  list.innerHTML = '<div class="check-item loading"><div class="check-icon">&#9711;</div><div><div class="check-name">檢查中…</div></div></div>';
  document.getElementById('btn-prereq-next').disabled = true;
  try {
    const data = await fetch('/api/prereqs').then(r => r.json());
    list.innerHTML = '';
    let allOk = true;
    data.checks.forEach(c => {
      if (!c.ok) allOk = false;
      const item = document.createElement('div');
      item.className = 'check-item ' + (c.ok ? 'ok' : 'err');
      item.innerHTML =
        `<div class="check-icon">${c.ok ? '&#10003;' : '&#10007;'}</div>` +
        `<div>` +
          `<div class="check-name"><code>${c.tool}</code></div>` +
          `<div class="check-ver">${c.version}</div>` +
        `</div>`;
      list.appendChild(item);
    });
    document.getElementById('prereq-warn').style.display = allOk ? 'none' : 'block';
    document.getElementById('btn-prereq-next').disabled = !allOk;
    S.prereqOk = allOk;
  } catch (e) {
    list.innerHTML = '<div class="check-item err"><div class="check-icon">&#10007;</div><div><div class="check-name">檢查失敗：' + e + '</div></div></div>';
  }
}

// ── Step 2: Database ──────────────────────────────────────────────────────────
function clearDbStatus() {
  const el = document.getElementById('db-status');
  el.className = 'db-status';
}

async function testDb() {
  const host = document.getElementById('db-host').value.trim();
  const port = document.getElementById('db-port').value.trim();
  const el = document.getElementById('db-status');
  el.className = 'db-status';
  el.textContent = '測試中...';
  el.style.display = 'block';
  try {
    const data = await fetch('/api/test-db', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, port }),
    }).then(r => r.json());
    el.className = 'db-status ' + (data.ok ? 'ok' : 'err');
    el.textContent = data.msg;
  } catch (e) {
    el.className = 'db-status err';
    el.textContent = '連線測試失敗：' + e;
  }
}

// ── Step 3: Manager ───────────────────────────────────────────────────────────
function checkPassMatch() {
  const p1 = document.getElementById('mgr-pass').value;
  const p2 = document.getElementById('mgr-pass2').value;
  const err = document.getElementById('err-mgr-pass2');
  if (p2 && p1 !== p2) err.classList.add('show');
  else err.classList.remove('show');
}

function validateManager() {
  let ok = true;
  const user = document.getElementById('mgr-user').value.trim();
  const pass = document.getElementById('mgr-pass').value;
  const pass2 = document.getElementById('mgr-pass2').value;

  const errUser = document.getElementById('err-mgr-user');
  const errPass = document.getElementById('err-mgr-pass');
  const errPass2 = document.getElementById('err-mgr-pass2');

  errUser.classList.toggle('show', !user); if (!user) ok = false;
  errPass.classList.toggle('show', pass.length < 8); if (pass.length < 8) ok = false;
  errPass2.classList.toggle('show', pass !== pass2); if (pass !== pass2) ok = false;

  if (ok) goNext();
}

// ── Step 4: Security ──────────────────────────────────────────────────────────
async function generateKey() {
  const data = await fetch('/api/generate-key').then(r => r.json());
  document.getElementById('secret-key').value = data.key;
  document.getElementById('err-secret-key').classList.remove('show');
}

function validateSecurity() {
  const key = document.getElementById('secret-key').value.trim();
  const err = document.getElementById('err-secret-key');
  if (!key) { err.classList.add('show'); return; }
  err.classList.remove('show');
  goNext();
}

// ── Step 5: Review ────────────────────────────────────────────────────────────
function buildReview() {
  const dbPass = document.getElementById('db-pass').value;
  const useSqlite = !document.getElementById('db-pass').value && !document.getElementById('db-host').value.trim();
  const rows = [
    ['系統目錄', S.sysRoot || '(未設定)'],
    ['資料庫主機', document.getElementById('db-host').value || '(SQLite)'],
    ['資料庫名稱', document.getElementById('db-name').value || '(SQLite)'],
    ['Manager 帳號', document.getElementById('mgr-user').value],
    ['Manager 密碼', '●●●●●●●●'],
    ['SECRET_KEY', document.getElementById('secret-key').value.slice(0,16) + '…'],
    ['CORS Origins', document.getElementById('cors-origins').value],
  ];
  const table = document.getElementById('review-table');
  table.innerHTML = rows.map(([k,v]) =>
    `<tr><td>${k}</td><td><strong>${v}</strong></td></tr>`
  ).join('');
}

// ── Step 6: Install ───────────────────────────────────────────────────────────
function buildEnv() {
  const host = document.getElementById('db-host').value.trim();
  const port = document.getElementById('db-port').value.trim();
  const name = document.getElementById('db-name').value.trim();
  const user = document.getElementById('db-user').value.trim();
  const pass = document.getElementById('db-pass').value;

  const env = {};

  if (pass) {
    env['DATABASE_URL'] = `postgresql+asyncpg://${user}:${pass}@${host}:${port}/${name}`;
    env['DB_HOST'] = host;
    env['DB_PORT'] = port;
    env['DB_NAME'] = name;
    env['DB_USERNAME'] = user;
    env['DB_PASSWORD'] = pass;
  }
  // else: no DATABASE_URL → backend auto-uses SQLite

  env['SECRET_KEY']    = document.getElementById('secret-key').value.trim();
  env['CORS_ORIGINS']  = document.getElementById('cors-origins').value.trim();
  env['BOOTSTRAP_MANAGER_ENABLED']              = 'true';
  env['BOOTSTRAP_MANAGER_TENANT_CODE']          = 'default';
  env['BOOTSTRAP_MANAGER_USERNAME']             = document.getElementById('mgr-user').value.trim();
  env['BOOTSTRAP_MANAGER_PASSWORD']             = document.getElementById('mgr-pass').value;
  env['BOOTSTRAP_MANAGER_MUST_CHANGE_PASSWORD'] = 'true';
  env['ENVIRONMENT'] = 'production';

  return env;
}

async function startInstall() {
  goStep(6);
  document.querySelector('#step-6 .card-title').textContent = '安裝中...';
  S.logOffset = 0;

  const env = buildEnv();
  const resp = await fetch('/api/install', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ env, sysRoot: S.sysRoot }),
  }).then(r => r.json());

  if (!resp.ok) {
    document.getElementById('log-box').textContent = '啟動失敗：' + resp.msg;
    return;
  }

  S.pollTimer = setInterval(pollLog, 800);
}

function pollLog() {
  fetch('/api/log?offset=' + S.logOffset)
    .then(r => r.json())
    .then(data => {
      if (data.lines.length > 0) {
        const box = document.getElementById('log-box');
        data.lines.forEach(line => {
          const el = document.createElement('div');
          if (line.startsWith('  OK'))           el.className = 'log-ok';
          else if (line.includes('[ERROR]'))      el.className = 'log-err';
          else if (line.startsWith('==='))        el.className = 'log-head';
          el.textContent = line;
          box.appendChild(el);
        });
        box.scrollTop = box.scrollHeight;
        S.logOffset = data.offset;
      }

      // Update step indicators
      const stepIdx = data.step_idx;
      ['ist-0','ist-1','ist-2','ist-3'].forEach((id, i) => {
        const el = document.getElementById(id);
        el.classList.remove('active','done','err');
        if (i < stepIdx)      el.classList.add('done');
        else if (i === stepIdx) el.classList.add('active');
      });

      if (!data.running && data.success !== null) {
        clearInterval(S.pollTimer);
        ['ist-0','ist-1','ist-2','ist-3'].forEach(id =>
          document.getElementById(id).classList.add(data.success ? 'done' : 'err')
        );
        setTimeout(() => showDone(data.success), 600);
      }
    })
    .catch(err => console.warn('poll error:', err));
}

function showDone(success) {
  goStep(7);
  document.getElementById('done-success').style.display = success ? 'block' : 'none';
  document.getElementById('done-error').style.display   = success ? 'none'  : 'block';
  if (success && S.sysRoot) {
    const py = S.sysRoot + (navigator.platform.toLowerCase().includes('win') ? '\\.venv\\Scripts\\python.exe' : '/.venv/bin/python');
    document.getElementById('start-cmd').textContent =
      'cd ' + S.sysRoot + '/backend\n' +
      py + ' -m uvicorn app.main:app --host 0.0.0.0 --port 8000';
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();
updateStepBar();
</script>
</body>
</html>"""

# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    global _sys_root_hint

    port = _DEFAULT_PORT
    no_browser = False
    args = sys.argv[1:]
    i = 0
    positional: list[str] = []
    while i < len(args):
        arg = args[i]
        if arg.startswith("--port="):
            port = int(arg.split("=", 1)[1])
        elif arg == "--port" and i + 1 < len(args):
            i += 1
            port = int(args[i])
        elif arg == "--no-browser":
            no_browser = True
        elif not arg.startswith("--"):
            positional.append(arg)
        i += 1

    if positional:
        p = Path(positional[0])
        if p.exists():
            _sys_root_hint = p.resolve()
        else:
            print(f"Warning: path not found: {p}", file=sys.stderr)

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    except OSError as e:
        print(f"Error: cannot bind to port {port}: {e}", file=sys.stderr)
        sys.exit(1)

    _server_ref[0] = server

    def _watchdog() -> None:
        """Shut down the server if the browser has been closed for >15 s and no install is running."""
        TIMEOUT = 15.0
        while True:
            time.sleep(5)
            hb = _last_heartbeat
            if hb == 0.0:
                continue  # heartbeat never received yet; wizard not opened
            with _lock:
                running = _install_state["running"]
            if not running and (time.time() - hb) > TIMEOUT:
                srv = _server_ref[0]
                if srv:
                    threading.Thread(target=srv.shutdown, daemon=True).start()
                break

    threading.Thread(target=_watchdog, daemon=True, name="heartbeat-watchdog").start()

    url = f"http://localhost:{port}/"

    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │   Form System 安裝精靈 (Install Wizard)      │")
    print("  ├─────────────────────────────────────────────┤")
    print(f"  │   URL : {url:<36}│")
    print("  │   按 Ctrl+C 停止伺服器                       │")
    print("  └─────────────────────────────────────────────┘")
    print()

    # Open browser after short delay
    if not no_browser:
        def _open() -> None:
            time.sleep(0.8)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  伺服器已停止。")


if __name__ == "__main__":
    main()
