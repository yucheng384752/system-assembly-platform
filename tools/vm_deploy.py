"""
Deploy frontend fixes to VM:
  192.168.200.33 / gslab / qqq123

Steps:
1. Upload fixed source files via SFTP
2. npm run build on VM
3. Kill + restart uvicorn
"""
import paramiko, os, stat, sys, time

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
DEPLOY_DIR = "/home/gslab/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26"
FRONTEND_DIR = f"{DEPLOY_DIR}/system/frontend"
BACKEND_DIR  = f"{DEPLOY_DIR}/system/backend"
VENV_PYTHON  = f"{DEPLOY_DIR}/system/.venv/bin/python"
LOG_FILE     = "/tmp/uvicorn.out"

# Local base: dist/client-deploy-gui-selected-form-system/system/frontend/src
LOCAL_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dist", "client-deploy-gui-selected-form-system", "system", "frontend", "src"
)

# Files to upload (relative to LOCAL_BASE → FRONTEND_DIR/src/)
FILES = [
    "App.tsx",
    "pages/FormsPage.tsx",
    "pages/ManagerPage.tsx",
    "pages/DeveloperLogsPage.tsx",
    "pages/upload/useUploadApi.ts",
    "components/common/Modal.tsx",
]


def run(client, cmd, desc="", timeout=120):
    print(f"\n[RUN] {desc or cmd}")
    chan = client.get_transport().open_session()
    chan.exec_command(cmd)
    out_buf, err_buf = b"", b""
    deadline = time.time() + timeout
    while not chan.exit_status_ready():
        if time.time() > deadline:
            print("[TIMEOUT]")
            chan.close()
            return -1, "", "timeout"
        if chan.recv_ready():
            chunk = chan.recv(4096)
            out_buf += chunk
            sys.stdout.write(chunk.decode(errors="replace"))
            sys.stdout.flush()
        if chan.recv_stderr_ready():
            err_buf += chan.recv_stderr(4096)
        time.sleep(0.05)
    # drain
    while chan.recv_ready():
        chunk = chan.recv(4096)
        out_buf += chunk
        sys.stdout.write(chunk.decode(errors="replace"))
        sys.stdout.flush()
    while chan.recv_stderr_ready():
        err_buf += chan.recv_stderr(4096)
    rc = chan.recv_exit_status()
    chan.close()
    if err_buf.strip():
        print(f"[STDERR] {err_buf.decode(errors='replace').strip()[:500]}")
    return rc, out_buf.decode(errors="replace"), err_buf.decode(errors="replace")


def upload_file(sftp, local_path, remote_path):
    remote_dir = os.path.dirname(remote_path)
    # ensure remote dir exists
    parts = remote_dir.replace("\\", "/").split("/")
    acc = ""
    for part in parts:
        if not part:
            continue
        acc = acc + "/" + part
        try:
            sftp.stat(acc)
        except FileNotFoundError:
            sftp.mkdir(acc)
    sftp.put(local_path, remote_path)
    print(f"  OK  {os.path.basename(local_path)} -> {remote_path}")


def main():
    print(f"=== Connecting to {HOST} ===")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=15)
    print("Connected.")

    # ── 1. Upload source files ──────────────────────────────────────────────
    print("\n=== Uploading source files ===")
    sftp = client.open_sftp()
    for rel in FILES:
        local  = os.path.join(LOCAL_BASE, rel.replace("/", os.sep))
        remote = f"{FRONTEND_DIR}/src/{rel}"
        if not os.path.exists(local):
            print(f"  SKIP (not found locally): {local}")
            continue
        upload_file(sftp, local, remote)
    sftp.close()

    # ── 2. npm run build ────────────────────────────────────────────────────
    print("\n=== Building frontend (npm run build) ===")
    rc, _, _ = run(
        client,
        f"cd {FRONTEND_DIR} && npm run build 2>&1",
        "npm run build",
        timeout=180,
    )
    if rc != 0:
        print(f"\n[ERROR] npm build failed (exit {rc}). Aborting.")
        client.close()
        sys.exit(1)

    # ── 3. Kill old uvicorn ─────────────────────────────────────────────────
    print("\n=== Restarting uvicorn ===")
    run(client, "pkill -f 'uvicorn app.main:app' || true", "kill old uvicorn", timeout=10)
    time.sleep(2)

    # ── 4. Start fresh uvicorn ──────────────────────────────────────────────
    start_cmd = (
        f"cd {BACKEND_DIR} && "
        f"ADMIN_API_KEYS='vm-admin-key-2026' "
        f"nohup {VENV_PYTHON} -m uvicorn app.main:app "
        f"--host 0.0.0.0 --port 8000 >> {LOG_FILE} 2>&1 &"
    )
    run(client, start_cmd, "start uvicorn", timeout=10)
    time.sleep(3)

    # ── 5. Verify ───────────────────────────────────────────────────────────
    print("\n=== Verifying ===")
    rc, out, _ = run(
        client,
        "ps aux | grep 'uvicorn app.main' | grep -v grep",
        "check process",
        timeout=10,
    )
    if "uvicorn" in out:
        print("\n[OK] uvicorn is running.")
    else:
        print("\n[WARN] uvicorn process not found -- check logs:")

    run(client, f"tail -20 {LOG_FILE}", "tail uvicorn log", timeout=10)

    # healthcheck
    rc, out, _ = run(
        client,
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/healthz",
        "healthz",
        timeout=15,
    )
    print(f"\nHealth check: HTTP {out.strip() or '???'}")

    client.close()
    print("\n=== Deploy complete ===", flush=True)


if __name__ == "__main__":
    main()
