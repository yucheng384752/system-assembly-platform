"""Upload and run a DB diagnostic on the VM."""
import paramiko, stat, time, os


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} environment variable is required (see tools/README-vm-scripts.md)")
    return value
HOST = "192.168.200.33"
USER = "gslab"
PASS = _require_env("VM_SSH_PASSWORD")
DEPLOY_DIR = "/home/gslab/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26"
BACKEND_DIR = f"{DEPLOY_DIR}/system/backend"
VENV = f"{DEPLOY_DIR}/system/.venv/bin/python"
REMOTE_SCRIPT = "/tmp/db_check.py"

DB_SCRIPT = '''
import sys, os
sys.path.insert(0, '.')
os.environ.setdefault("ENV_FILE", "/home/gslab/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26/system/.env")

from sqlalchemy import create_engine, text
from app.core.config import get_settings

s = get_settings()
url = str(s.database_url).replace("+asyncpg", "")
try:
    eng = create_engine(url)
except Exception:
    # fallback: try psycopg2
    url = str(s.database_url).replace("+asyncpg", "+psycopg2")
    eng = create_engine(url)

with eng.connect() as c:
    print("=== generic_records total ===")
    total = c.execute(text("SELECT COUNT(*) FROM generic_records")).scalar()
    print(f"  total: {total}")

    print()
    print("=== generic_records by station_id ===")
    rows = c.execute(text(
        "SELECT gr.station_id, s.code AS station_code, s.tenant_id AS s_tenant, "
        "gr.tenant_id AS gr_tenant, COUNT(*) AS n "
        "FROM generic_records gr "
        "LEFT JOIN stations s ON s.id = gr.station_id "
        "GROUP BY gr.station_id, s.code, s.tenant_id, gr.tenant_id "
        "ORDER BY n DESC"
    )).fetchall()
    if rows:
        for r in rows:
            print(f"  station_id={r[0]}, code={r[1]}, s_tenant={r[2]}, gr_tenant={r[3]}, n={r[4]}")
    else:
        print("  (empty)")

    print()
    print("=== stations ===")
    rows = c.execute(text(
        "SELECT id, code, tenant_id FROM stations ORDER BY code"
    )).fetchall()
    for r in rows:
        print(f"  id={r[0]}, code={r[1]}, tenant_id={r[2]}")

    print()
    print("=== tenants ===")
    rows = c.execute(text("SELECT id, code, is_default FROM tenants")).fetchall()
    for r in rows:
        print(f"  id={r[0]}, code={r[1]}, default={r[2]}")

    print()
    print("=== latest import_jobs ===")
    rows = c.execute(text(
        "SELECT id, table_code, tenant_id, status, created_at "
        "FROM import_jobs ORDER BY created_at DESC LIMIT 5"
    )).fetchall()
    for r in rows:
        print(f"  id={r[0]}, table_code={r[1]}, tenant_id={r[2]}, status={r[3]}")

    print()
    print("=== generic_records sample (first 3) ===")
    rows = c.execute(text(
        "SELECT id, station_id, tenant_id, lot_no_raw, data FROM generic_records LIMIT 3"
    )).fetchall()
    for r in rows:
        print(f"  id={r[0]}, station_id={r[1]}, tenant_id={r[2]}, lot_no={r[3]}")
        print(f"    data={str(r[4])[:200]}")
'''

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.WarningPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

# Upload script
sftp = client.open_sftp()
with sftp.file(REMOTE_SCRIPT, "w") as f:
    f.write(DB_SCRIPT)
sftp.chmod(REMOTE_SCRIPT, stat.S_IRWXU)
sftp.close()
print(f"Uploaded {REMOTE_SCRIPT}")

# Run it
print(f"\n=== Running DB check ===")
cmd = f"cd {BACKEND_DIR} && {VENV} {REMOTE_SCRIPT} 2>&1"
_, stdout, stderr = client.exec_command(cmd, timeout=30)
print(stdout.read().decode(errors="replace"))
err = stderr.read().decode(errors="replace")
if err.strip():
    print(f"[ERR] {err[:500]}")

client.close()
