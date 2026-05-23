import paramiko, time

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
DEPLOY_DIR = "deploy-test-v12"
DEST = f"/home/gslab/{DEPLOY_DIR}"

def run(ssh, cmd, timeout=60):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err

def p(s):
    print(s.encode("ascii", "replace").decode("ascii"))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

# Check PostgreSQL is up
p("=== PostgreSQL port ===")
rc, out, err = run(ssh, "ss -tlnp | grep 5432")
p(out or "(not listening)")

# Kill old backend
run(ssh, "pkill -f 'uvicorn app.main' 2>/dev/null || true")
time.sleep(1)

# Clear old log
run(ssh, f"rm -f {DEST}/system/logs/backend.log {DEST}/system/logs/backend.pid")

# Start via deploy.sh --background
p("=== Starting backend (deploy.sh --background) ===")
rc, out, err = run(ssh, f"cd {DEST} && bash deploy.sh --background 2>&1", timeout=120)
p(f"rc={rc}")

# Wait for startup
p("Waiting 10s...")
time.sleep(10)

# Log
p("\n=== Backend log (last 50 lines) ===")
rc, out, err = run(ssh, f"tail -50 {DEST}/system/logs/backend.log 2>/dev/null || echo 'no log'")
p(out)

# Health
p("=== Health check ===")
rc, out, err = run(ssh, "curl -s -w '\\nHTTP:%{http_code}' http://localhost:8000/healthz", timeout=10)
p(out)

# Process
p("=== uvicorn process ===")
rc, out, err = run(ssh, "ps aux | grep uvicorn | grep -v grep")
p(out or "(no uvicorn)")

ssh.close()
