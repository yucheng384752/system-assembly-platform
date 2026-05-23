import paramiko

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

p("=== deploy state ===")
rc, out, err = run(ssh, f"find {DEST} -maxdepth 3 -type f | sort | head -80")
p(out or err)

p("=== processes ===")
rc, out, err = run(ssh, "ps aux | egrep 'deploy.sh|pip|npm|node|uvicorn|python' | grep -v egrep")
p(out or "(none)")

p("=== cors config ===")
rc, out, err = run(ssh, f"grep -n \"raw == '\\[\\*\\]'\\|json.loads\\|cors_origins\" {DEST}/system/backend/app/core/config.py 2>&1")
p(out or err)

p("=== env ===")
rc, out, err = run(ssh, f"cat {DEST}/system/.env 2>&1")
p(out or err)

ssh.close()
