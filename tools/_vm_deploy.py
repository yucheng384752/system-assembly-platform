import paramiko, time

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"

def run(ssh, cmd, timeout=120):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    rc = stdout.channel.recv_exit_status()
    return rc, out, err

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

DEPLOY_DIR = "deploy-test-v12"
ZIP = "/home/gslab/client-deploy-mvp-import-flow-v12.zip"
DEST = f"/home/gslab/{DEPLOY_DIR}"

# Clean up old dir
run(ssh, f"rm -rf {DEST}")

# Extract: dest first, src second
print("=== Extracting ZIP ===")
rc, out, err = run(ssh, f"python3 /home/gslab/extract_zip.py {DEST} {ZIP}", timeout=60)
print(f"rc={rc}")
print(out or err)

# Check contents
rc, out, err = run(ssh, f"ls {DEST}/")
print("Contents:", out.strip())

# Kill any previous test backend
run(ssh, "pkill -f 'uvicorn app.main' 2>/dev/null || true")
time.sleep(1)

# Write .env
print("\n=== Writing .env ===")
env_content = (
    "DATABASE_URL=postgresql+asyncpg://gslab:qqq123@localhost:5432/formdb\n"
    "SECRET_KEY=test_secret_key_at_least_32_characters_long\n"
    "AUTH_MODE=api_key\n"
    "ENVIRONMENT=development\n"
    "LOG_LEVEL=INFO\n"
    'CORS_ORIGINS=["*"]\n'
)
rc, out, err = run(ssh, f"cat > {DEST}/system/.env << 'ENVEOF'\n{env_content}ENVEOF")
print(f"rc={rc}", err or "ok")

print("\n=== Running deploy.sh --background ===")
rc, out, err = run(ssh, f"cd {DEST} && bash deploy.sh --background 2>&1", timeout=180)
print(f"rc={rc}")
print(out[-3000:] if len(out) > 3000 else out)
if err:
    print("STDERR:", err[-500:])

# Wait for backend to settle
print("\n=== Waiting 6s for backend ===")
time.sleep(6)

# Check backend log
print("\n=== Backend log (last 40 lines) ===")
rc, out, err = run(ssh, f"tail -40 {DEST}/system/logs/backend.log 2>/dev/null || echo 'no log'")
print(out)

# Health check
print("\n=== Health check ===")
rc, out, err = run(ssh, "curl -s -o /dev/null -w 'HTTP:%{http_code}' http://localhost:8000/healthz")
print("Health:", out)

ssh.close()
