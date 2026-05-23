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

# Kill old backend
run(ssh, "pkill -f 'uvicorn app.main' 2>/dev/null || true")
time.sleep(1)

# Clear old log
run(ssh, f"rm -f {DEST}/system/logs/backend.log {DEST}/system/logs/backend.pid")

# Start backend via deploy.sh --background
p("=== Starting backend ===")
rc, out, err = run(ssh, f"cd {DEST} && bash deploy.sh --background 2>&1", timeout=120)
p(f"deploy.sh rc={rc}")

time.sleep(8)

# Check log
p("\n=== Backend log (last 30 lines) ===")
rc, out, err = run(ssh, f"tail -30 {DEST}/system/logs/backend.log 2>/dev/null || echo 'no log'")
p(out)

# Health
p("=== Health check ===")
rc, out, err = run(ssh, "curl -s -o /dev/null -w 'HTTP:%{http_code}' http://localhost:8000/healthz", timeout=10)
p("Health: " + out)

# Full health response
p("=== /healthz response ===")
rc, out, err = run(ssh, "curl -s http://localhost:8000/healthz", timeout=10)
p(out)

# Process check
p("=== uvicorn process ===")
rc, out, err = run(ssh, "ps aux | grep uvicorn | grep -v grep")
p(out or "(no uvicorn)")

ssh.close()
