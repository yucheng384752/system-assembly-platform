r"""
Windows 端對端部署測試
1. SSH 連 VM -> 建立 formdb_wintest 測試 DB
2. Paramiko SSH tunnel: 127.0.0.1:15432 -> VM:5432
3. 解壓 client-deploy ZIP 到 C:\Temp\form-win-test
4. 寫 system\.env (DATABASE_URL -> 127.0.0.1:15432/formdb_wintest)
5. 執行 deploy.ps1 -Background -SkipFrontend
6. 等待 http://127.0.0.1:8000/healthz HTTP 200
7. 插入 tenant / api_key / table_registry (via SSH psql)
8. E2E API 測試
9. 清理
"""

import hashlib
import hmac as _hmac
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import zipfile


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} environment variable is required (see tools/README-vm-scripts.md)")
    return value
import paramiko

# ── Config ────────────────────────────────────────────────────────────────────
VM_HOST = "192.168.200.33"
VM_USER = "gslab"
VM_PASS = _require_env("VM_SSH_PASSWORD")
DB_USER = "gslab"
DB_PASS = _require_env("VM_SSH_PASSWORD")
DB_NAME = "formdb_wintest"
TUNNEL_PORT = 15432

ZIP_PATH = os.environ.get("WIN_TEST_ZIP_PATH") or os.path.join(
    os.path.dirname(__file__), "..", "dist", "client-deploy-mvp-import-flow.zip"
)
ZIP_PATH = os.path.abspath(ZIP_PATH)

TEMP_DIR = r"C:\Temp\form-win-test"
BACKEND_PORT = int(os.environ.get("WIN_TEST_BACKEND_PORT") or 8000)
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"

SECRET_KEY = "test_secret_key_at_least_32_characters_long"
RAW_KEY = "e2e-test-api-key-v1"

PASS_COUNT = 0
FAIL_COUNT = 0


# ── Helpers ───────────────────────────────────────────────────────────────────
def p(s):
    print(str(s).encode("ascii", "replace").decode("ascii"), flush=True)


def section(title):
    p(f"\n{'='*60}")
    p(f"  {title}")
    p(f"{'='*60}")


def check(name, passed, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    status = "PASS" if passed else "FAIL"
    suffix = f" | {detail}" if detail else ""
    p(f"  [{status}] {name}{suffix}")
    return passed


def run_ssh(ssh, cmd, timeout=120):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def psql(ssh, sql, dbname=None):
    db = dbname or DB_NAME
    safe = sql.replace("'", "'\"'\"'")
    cmd = f"PGPASSWORD={DB_PASS} psql -U {DB_USER} -h localhost -d {db} -t -c '{safe}'"
    return run_ssh(ssh, cmd, timeout=15)


def wait_backend(url, timeout_s=120):
    deadline = time.time() + timeout_s
    import urllib.request, urllib.error
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def http_get(url, headers=None):
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


def http_post_multipart(url, headers, fields, files):
    """Simple multipart/form-data POST using http.client."""
    import http.client, urllib.parse, random, string

    boundary = "".join(random.choices(string.ascii_letters + string.digits, k=32))
    body_parts = []
    for k, v in fields.items():
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
            f"{v}\r\n"
        )
    for field_name, (filename, data) in files.items():
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
        )
        body_parts.append(data if isinstance(data, bytes) else data.encode("utf-8"))
        body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n")

    body = b"".join(p.encode("utf-8") if isinstance(p, str) else p for p in body_parts)
    content_type = f"multipart/form-data; boundary={boundary}"

    parsed = urllib.parse.urlparse(url)
    conn = http.client.HTTPConnection(parsed.netloc, timeout=30)
    all_headers = {**headers, "Content-Type": content_type, "Content-Length": str(len(body))}
    conn.request("POST", parsed.path, body=body, headers=all_headers)
    resp = conn.getresponse()
    return resp.status, resp.read().decode("utf-8", errors="replace")


# ── SSH Tunnel ────────────────────────────────────────────────────────────────
class SSHTunnel:
    def __init__(self, ssh_client, local_port, remote_host, remote_port):
        self._transport = ssh_client.get_transport()
        self._local_port = local_port
        self._remote_host = remote_host
        self._remote_port = remote_port
        self._server_sock = None

    def _copy(self, src, dst):
        try:
            while True:
                data = src.recv(4096)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            for s in (src, dst):
                try:
                    s.close()
                except Exception:
                    pass

    def _handle(self, client_sock):
        try:
            peer = client_sock.getpeername()
            chan = self._transport.open_channel(
                "direct-tcpip", (self._remote_host, self._remote_port), peer
            )
        except Exception as e:
            p(f"  [tunnel] open_channel error: {e}")
            client_sock.close()
            return
        t1 = threading.Thread(target=self._copy, args=(client_sock, chan), daemon=True)
        t2 = threading.Thread(target=self._copy, args=(chan, client_sock), daemon=True)
        t1.start()
        t2.start()

    def _accept_loop(self):
        while self._server_sock:
            try:
                client_sock, _ = self._server_sock.accept()
                threading.Thread(target=self._handle, args=(client_sock,), daemon=True).start()
            except Exception:
                break

    def start(self):
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(("127.0.0.1", self._local_port))
        self._server_sock.listen(10)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        p(
            f"  SSH tunnel: 127.0.0.1:{self._local_port}"
            f" -> {self._remote_host}:{self._remote_port}"
        )

    def stop(self):
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None


# ── Main ──────────────────────────────────────────────────────────────────────
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
ssh.connect(VM_HOST, username=VM_USER, password=VM_PASS, timeout=15)
p(f"Connected to {VM_HOST}")

tunnel = SSHTunnel(ssh, TUNNEL_PORT, "127.0.0.1", 5432)
backend_proc = None

try:
    # ── Phase 1: Prepare VM DB ───────────────────────────────────────────────
    section("Phase 1: Prepare VM database")

    rc, out, err = run_ssh(
        ssh,
        f"PGPASSWORD={DB_PASS} dropdb -U {DB_USER} -h localhost --if-exists {DB_NAME}",
        timeout=15,
    )
    check("dropdb formdb_wintest (if exists)", rc == 0, err.strip() or "ok")

    rc, out, err = run_ssh(
        ssh,
        f"PGPASSWORD={DB_PASS} createdb -U {DB_USER} -h localhost {DB_NAME}",
        timeout=15,
    )
    check("createdb formdb_wintest", rc == 0, err.strip() or "ok")

    # ── Phase 2: Start SSH tunnel ────────────────────────────────────────────
    section("Phase 2: SSH tunnel 127.0.0.1:15432 -> VM:5432")
    tunnel.start()

    # Verify tunnel works
    try:
        s = socket.create_connection(("127.0.0.1", TUNNEL_PORT), timeout=3)
        s.close()
        check("tunnel reachable", True, f"127.0.0.1:{TUNNEL_PORT}")
    except Exception as e:
        check("tunnel reachable", False, str(e))

    # ── Phase 3: Extract ZIP ─────────────────────────────────────────────────
    section("Phase 3: Extract ZIP")

    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR, exist_ok=True)

    check("ZIP exists", os.path.isfile(ZIP_PATH), ZIP_PATH)

    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(TEMP_DIR)

    sys_dir = os.path.join(TEMP_DIR, "system")
    backend_dir = os.path.join(sys_dir, "backend")
    check("system dir exists", os.path.isdir(sys_dir), sys_dir)
    check("requirements.txt exists", os.path.isfile(os.path.join(backend_dir, "requirements.txt")), "")

    # deploy.ps1 hardcodes uvicorn's port; repoint it when WIN_TEST_BACKEND_PORT
    # overrides the default (e.g. to avoid a port already bound by another
    # process on this machine).
    if BACKEND_PORT != 8000:
        deploy_ps1_path = os.path.join(TEMP_DIR, "deploy.ps1")
        with open(deploy_ps1_path, encoding="utf-8") as f:
            deploy_src = f.read()
        old_port = '"--host", "127.0.0.1", "--port", "8000"'
        new_port = f'"--host", "127.0.0.1", "--port", "{BACKEND_PORT}"'
        check("found uvicorn port to repoint in deploy.ps1", old_port in deploy_src, "")
        deploy_src = deploy_src.replace(old_port, new_port, 1)
        with open(deploy_ps1_path, "w", encoding="utf-8") as f:
            f.write(deploy_src)
        p(f"  Repointed deploy.ps1 uvicorn port to {BACKEND_PORT}")

    # ── Phase 4: Write .env ──────────────────────────────────────────────────
    section("Phase 4: Write .env")

    env_content = "\n".join(
        [
            f"DATABASE_URL=postgresql+asyncpg://{DB_USER}:{DB_PASS}@127.0.0.1:{TUNNEL_PORT}/{DB_NAME}",
            f"SECRET_KEY={SECRET_KEY}",
            "AUTH_MODE=api_key",
            "ENVIRONMENT=development",
            "LOG_LEVEL=INFO",
            "CORS_ORIGINS=http://localhost:5173,http://localhost:3000",
            "MULTI_TENANT_ENABLED=false",
            "AUDIT_EVENTS_ENABLED=false",
            "USE_GENERIC_SCHEMA=false",
            "VALID_MATERIALS_CSV=PE,PP,PET,OPP,CPP,NY",
            "VALID_SLITTING_MACHINES_CSV=1,2,3,4,5,6,7,8,9,10",
            "",
        ]
    )
    env_path = os.path.join(sys_dir, ".env")
    with open(env_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(env_content)
    check("write system\\.env", os.path.isfile(env_path), env_path)

    # ── Phase 5: Run deploy.ps1 -Background -SkipFrontend ───────────────────
    section("Phase 5: Run deploy.ps1 -Background -SkipFrontend")

    deploy_ps1 = os.path.join(TEMP_DIR, "deploy.ps1")
    check("deploy.ps1 exists", os.path.isfile(deploy_ps1), deploy_ps1)

    p("  Running deploy.ps1 -Background -SkipFrontend (pip install may take 5-10 min)...")
    ps1_log = os.path.join(TEMP_DIR, "deploy-ps1.log")
    deploy_rc = None
    with open(ps1_log, "w", encoding="utf-8", errors="replace") as log_fh:
        deploy_proc = subprocess.Popen(
            [
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-File", deploy_ps1,
                "-Background",
                "-SkipFrontend",
            ],
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL,
            cwd=TEMP_DIR,
        )
    try:
        deploy_rc = deploy_proc.wait(timeout=900)
    except subprocess.TimeoutExpired:
        deploy_proc.kill()
        deploy_rc = -1
        p("  [WARN] deploy.ps1 took > 900s; killed. Backend may still be running.")
    check("deploy.ps1 exit code 0", deploy_rc == 0, f"rc={deploy_rc}")
    if deploy_rc != 0:
        if os.path.isfile(ps1_log):
            with open(ps1_log, encoding="utf-8", errors="replace") as f:
                tail = f.read()[-2000:]
            p("  --- deploy.ps1 log tail ---")
            for line in tail.splitlines()[-20:]:
                p(f"  {line}")

    # ── Phase 6: Wait for backend ────────────────────────────────────────────
    section("Phase 6: Wait for backend on localhost:8000")

    p("  Waiting up to 30s for http://127.0.0.1:8000/healthz ...")
    ok_health = wait_backend(f"{BACKEND_URL}/healthz", timeout_s=30)
    check("backend reachable (healthz HTTP 200)", ok_health, "")

    if not ok_health:
        # Show backend log tail for diagnosis
        log_path = os.path.join(sys_dir, "logs", "backend.out.log")
        err_path = os.path.join(sys_dir, "logs", "backend.err.log")
        for lp in (log_path, err_path):
            if os.path.isfile(lp):
                with open(lp, encoding="utf-8", errors="replace") as lf:
                    tail = lf.read()[-2000:]
                p(f"  --- {os.path.basename(lp)} ---")
                for line in tail.splitlines()[-20:]:
                    p(f"  {line}")
        raise SystemExit("Backend did not start; aborting further tests.")

    status_code, body = http_get(f"{BACKEND_URL}/healthz")
    check("GET /healthz HTTP 200", status_code == 200, body[:80])

    # ── Phase 7: Insert test data via SSH ────────────────────────────────────
    section("Phase 7: Insert test data (tenant, api_key, table_registry)")

    key_hash = _hmac.new(
        SECRET_KEY.encode("utf-8"), RAW_KEY.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    tenant_id_new = str(uuid.uuid4())
    api_key_id_new = str(uuid.uuid4())

    sql_tenant = (
        f"INSERT INTO tenants (id, name, code, is_active, is_default) "
        f"VALUES ('{tenant_id_new}', 'Win E2E Tenant', 'win-e2e', true, true) "
        f"ON CONFLICT (code) DO NOTHING;"
    )
    rc, _, err = psql(ssh, sql_tenant)
    check("insert tenant", rc == 0, err.strip() or "ok")

    rc, out, _ = psql(ssh, "SELECT id FROM tenants WHERE code='win-e2e';")
    tenant_id = out.strip().splitlines()[0].strip() if out.strip() else ""
    check("resolve tenant id", bool(tenant_id), tenant_id[:36])

    sql_key = (
        f"INSERT INTO tenant_api_keys (id, tenant_id, key_hash, label, is_active) "
        f"VALUES ('{api_key_id_new}', '{tenant_id}', '{key_hash}', 'win-e2e-key', true) "
        f"ON CONFLICT (key_hash) DO NOTHING;"
    )
    rc, _, err = psql(ssh, sql_key)
    check("insert api key", rc == 0, err.strip() or "ok")

    for tc, dn in [("P1", "P1 Form Records"), ("P2", "P2 Form Records"), ("P3", "P3 Form Records")]:
        sql_tr = (
            f"INSERT INTO table_registry (id, table_code, display_name) "
            f"VALUES (gen_random_uuid(), '{tc}', '{dn}') "
            f"ON CONFLICT (table_code) DO NOTHING;"
        )
        rc, _, err = psql(ssh, sql_tr)
        check(f"insert table_registry({tc})", rc == 0, err.strip() or "ok")

    # ── Phase 8: E2E API Tests ────────────────────────────────────────────────
    section("Phase 8: E2E API Tests")

    api_headers = {"X-API-Key": RAW_KEY}

    # POST /api/upload
    csv_data = "name,value\nrow_a,1\nrow_b,2\nrow_c,3\n"
    status_code, body = http_post_multipart(
        f"{BACKEND_URL}/api/upload",
        api_headers,
        {},
        {"file": ("P1_2507173_01.csv", csv_data)},
    )
    process_id = None
    try:
        data = json.loads(body)
        process_id = data.get("process_id")
        total_rows = data.get("total_rows", -1)
        valid_rows = data.get("valid_rows", -1)
        upload_ok = status_code == 200 and bool(process_id) and total_rows == 3
        check(
            "POST /api/upload",
            upload_ok,
            f"HTTP:{status_code} rows={total_rows}/{valid_rows}",
        )
    except Exception:
        check("POST /api/upload", False, f"HTTP:{status_code} body={body[:120]}")

    # GET /api/upload/{id}/status
    if process_id:
        status_code, body = http_get(
            f"{BACKEND_URL}/api/upload/{process_id}/status", api_headers
        )
        try:
            data = json.loads(body)
            status_val = data.get("status", "")
            status_ok = status_code == 200 and status_val in (
                "VALIDATED", "PENDING", "COMPLETED"
            )
            check(
                "GET /api/upload/{id}/status",
                status_ok,
                f"HTTP:{status_code} status={status_val}",
            )
        except Exception:
            check(
                "GET /api/upload/{id}/status",
                status_code == 200,
                f"HTTP:{status_code} body={body[:120]}",
            )
    else:
        check("GET /api/upload/{id}/status", False, "skipped: no process_id")

    # POST /api/v2/import/jobs
    import_csv = "lot_no,value\n2507173_01,101\n2507173_01,102\n2507173_01,103\n"
    ts = int(time.time())
    status_code, body = http_post_multipart(
        f"{BACKEND_URL}/api/v2/import/jobs",
        api_headers,
        {"table_code": "P1", "allow_duplicate": "true"},
        {f"files": (f"P1_2507173_01_{ts}.csv", import_csv)},
    )
    import_job_id = None
    try:
        data = json.loads(body)
        import_job_id = data.get("id")
        job_ok = status_code == 201 and bool(import_job_id)
        check(
            "POST /api/v2/import/jobs",
            job_ok,
            f"HTTP:{status_code} id={str(import_job_id)[:8]}...",
        )
    except Exception:
        check("POST /api/v2/import/jobs", False, f"HTTP:{status_code} body={body[:120]}")

    # Wait for import job READY
    if import_job_id:
        deadline = time.time() + 45
        last_status = ""
        while time.time() < deadline:
            sc, body2 = http_get(
                f"{BACKEND_URL}/api/v2/import/jobs/{import_job_id}", api_headers
            )
            if sc == 200:
                last_status = json.loads(body2).get("status", "") if body2 else ""
                if last_status in ("READY", "COMPLETED"):
                    break
                if last_status == "FAILED":
                    break
            time.sleep(2)
        check(
            "import job reaches READY/COMPLETED",
            last_status in ("READY", "COMPLETED"),
            f"status={last_status}",
        )

finally:
    # ── Cleanup ──────────────────────────────────────────────────────────────
    section("Cleanup")

    # Kill backend
    pid_path = os.path.join(TEMP_DIR, "system", "runtime", "backend.pid")
    killed = False
    if os.path.isfile(pid_path):
        try:
            with open(pid_path, encoding="utf-8-sig", errors="replace") as f:
                pid = int(f.read().strip())
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10,
            )
            p(f"  Killed backend PID={pid}")
            killed = True
        except Exception as e:
            p(f"  Could not kill by PID: {e}")
    if not killed:
        # Best-effort kill any uvicorn on port 8000
        subprocess.run(
            ["powershell.exe", "-Command",
             f"Get-NetTCPConnection -LocalPort {BACKEND_PORT} -State Listen "
             f"-ErrorAction SilentlyContinue | "
             f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force "
             f"-ErrorAction SilentlyContinue }}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
        )
        p(f"  Killed processes on port {BACKEND_PORT}")

    # Drop test DB
    try:
        rc, out, err = run_ssh(
            ssh,
            f"PGPASSWORD={DB_PASS} dropdb -U {DB_USER} -h localhost --if-exists {DB_NAME}",
            timeout=15,
        )
        p(f"  dropdb {DB_NAME}: rc={rc}")
    except Exception as e:
        p(f"  dropdb error: {e}")

    # Stop tunnel
    tunnel.stop()

    # Remove temp dir
    try:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        p(f"  Removed {TEMP_DIR}")
    except Exception as e:
        p(f"  Could not remove {TEMP_DIR}: {e}")

    ssh.close()

    section("Results")
    p(f"  PASS: {PASS_COUNT}")
    p(f"  FAIL: {FAIL_COUNT}")
    p(f"  {'ALL PASS' if FAIL_COUNT == 0 else 'SOME FAILED'}")
    sys.exit(0 if FAIL_COUNT == 0 else 1)
