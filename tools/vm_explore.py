"""Quick VM exploration via paramiko."""
import os
import paramiko, sys


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} environment variable is required (see tools/README-vm-scripts.md)")
    return value
HOST = "192.168.200.33"
USER = "gslab"
PASS = _require_env("VM_SSH_PASSWORD")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.WarningPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

cmds = [
    "ls ~/Desktop/",
    "ls ~/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26/ 2>/dev/null || echo 'DIR NOT FOUND'",
    "ls ~/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26/system/ 2>/dev/null",
    "ls ~/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26/system/frontend/ 2>/dev/null",
    "ls ~/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26/system/frontend/dist/ 2>/dev/null || echo 'no dist'",
    "ls ~/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26/system/backend/app/static/ 2>/dev/null || echo 'no static'",
    "which node && node --version && which npm && npm --version",
    "ps aux | grep -E 'uvicorn|python' | grep -v grep | head -5",
    "cat /etc/systemd/system/form-system*.service 2>/dev/null | head -30 || echo 'no systemd service'",
    "ls /home/gslab/Desktop/ | grep form",
]

for cmd in cmds:
    print(f"\n$ {cmd}")
    _, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out)
    if err: print(f"[ERR] {err}")

client.close()
