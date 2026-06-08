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
import threading
import time
import webbrowser
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
_DEFAULT_PORT = 9981
_HERE = Path(__file__).parent.resolve()

# ── Global state ──────────────────────────────────────────────────────────────
_lock = threading.Lock()
_install_state: dict = {
    "running": False,
    "log": [],
    "step_idx": -1,
    "success": None,
}
_sys_root_hint: Path | None = None

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


def _venv_bin(sys_root: Path, name: str) -> Path:
    if platform.system() == "Windows":
        return sys_root / ".venv" / "Scripts" / (name + ".exe")
    return sys_root / ".venv" / "bin" / name


def _write_env(sys_root: Path, values: dict) -> None:
    lines: list[str] = []
    for k, v in values.items():
        safe = str(v).replace("\\", "\\\\").replace("'", "\\'")
        lines.append(f"{k}='{safe}'")
    (sys_root / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


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

        # Step 1: Create venv
        step(1, "建立 Python 虛擬環境")
        rc = _run_cmd(
            [sys.executable, "-m", "venv", "--clear", str(sys_root / ".venv")],
            sys_root,
        )
        if rc != 0:
            raise RuntimeError(f"venv 建立失敗 (exit {rc})")
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
    <div class="nav-row">
      <button class="btn btn-secondary" onclick="goStep(4)">&larr; 上一步</button>
      <button class="btn btn-primary" onclick="startInstall()">&#9658; 開始安裝</button>
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
  } catch (e) {
    console.error('init error:', e);
  }
}

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

// ── Navigation ────────────────────────────────────────────────────────────────
function goStep(n) {
  document.getElementById('step-' + S.currentStep).style.display = 'none';
  S.currentStep = n;
  document.getElementById('step-' + n).style.display = 'block';
  updateStepBar();
  window.scrollTo(0, 0);
  if (n === 1) runPrereqs();
  if (n === 5) buildReview();
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
