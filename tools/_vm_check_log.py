import paramiko, time

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
DEPLOY_DIR = "deploy-test-v12"
DEST = f"/home/gslab/{DEPLOY_DIR}"

def run(ssh, cmd, timeout=30):
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

p("=== Backend log (last 50 lines) ===")
rc, out, err = run(ssh, f"tail -50 {DEST}/system/logs/backend.log 2>/dev/null || echo 'no log'")
p(out)

p("=== Deploy log (last 120 lines) ===")
rc, out, err = run(ssh, "tail -120 /tmp/deploy-v12.log 2>/dev/null || echo 'no deploy log'")
p(out)

p("=== Health check ===")
rc, out, err = run(ssh, "curl -s -o /dev/null -w 'HTTP:%{http_code}' http://localhost:8000/healthz")
p("Health: " + out)

p("=== PID file ===")
rc, out, err = run(ssh, f"cat {DEST}/system/logs/backend.pid 2>/dev/null || echo 'no pid'")
p("PID: " + out.strip())

p("=== Process ===")
rc, out, err = run(ssh, "ps aux | grep uvicorn | grep -v grep")
p(out or "(no uvicorn process)")

ssh.close()
