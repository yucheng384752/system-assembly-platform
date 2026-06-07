import paramiko

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
DEPLOY_DIR = "deploy-test-v12"
DEST = f"/home/gslab/{DEPLOY_DIR}"
BACKEND = f"{DEST}/system/backend"

def run(ssh, cmd, timeout=30):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err

def write_file(ssh, path, content):
    sftp = ssh.open_sftp()
    import io
    sftp.putfo(io.BytesIO(content.encode("utf-8")), path)
    sftp.close()

def p(s):
    print(s.encode("ascii", "replace").decode("ascii"))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

# 1. Create app/config/
run(ssh, f"mkdir -p {BACKEND}/app/config")

# 2. Write app/config/__init__.py
write_file(ssh, f"{BACKEND}/app/config/__init__.py", "")

# 3. Write app/config/constants.py stub
constants_content = '''# Stub constants for validation service
VALID_MATERIALS: list[str] = []
VALID_SLITTING_MACHINES: list[str] = []

def get_material_list() -> list[str]:
    return VALID_MATERIALS

def get_slitting_machine_list() -> list[str]:
    return VALID_SLITTING_MACHINES
'''
write_file(ssh, f"{BACKEND}/app/config/constants.py", constants_content)
p("Created app/config/constants.py")

# 4. Verify
rc, out, err = run(ssh, f"ls {BACKEND}/app/config/")
p("config/ contents: " + out.strip())

# 5. Now try to import the app to see if there are more errors
p("\n=== Testing import (python -c) ===")
rc, out, err = run(ssh, f"cd {BACKEND} && {DEST}/system/.venv/bin/python -c 'import app.main' 2>&1", timeout=30)
p(f"rc={rc}")
p(out[-2000:] if len(out) > 2000 else out)

ssh.close()
