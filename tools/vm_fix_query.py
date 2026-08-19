"""
Fix commit_job bug + migrate existing staging_rows to generic_records on VM.
Steps:
1. Upload fixed services/import_v2.py
2. Upload migration script
3. Run migration (staging_rows → generic_records for completed jobs)
4. Restart uvicorn
5. Verify
"""
import paramiko, stat, time, sys


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
LOG_FILE = "/tmp/uvicorn.out"

import os
LOCAL_SERVICE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dist", "client-deploy-gui-selected-form-system",
    "system", "backend", "app", "services", "import_v2.py"
)

MIGRATION_SCRIPT = r'''
"""Migrate completed staging_rows -> generic_records."""
import asyncio, sys, uuid, os
sys.path.insert(0, ".")
os.environ.setdefault(
    "ENV_FILE",
    "/home/gslab/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26/system/.env"
)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.core.config import get_settings
from datetime import datetime, timezone

async def main():
    s = get_settings()
    engine = create_async_engine(str(s.database_url), echo=False)

    async with AsyncSession(engine) as db:
        # Get all COMPLETED import_jobs
        result = await db.execute(text(
            "SELECT ij.id, ij.table_id, ij.tenant_id, tr.table_code "
            "FROM import_jobs ij "
            "JOIN table_registry tr ON tr.id = ij.table_id "
            "WHERE ij.status = 'COMPLETED'"
        ))
        jobs = result.fetchall()
        print(f"Found {len(jobs)} COMPLETED import_jobs")

        total_migrated = 0
        for job_id, table_id, tenant_id, table_code in jobs:
            # Get station
            st_result = await db.execute(text(
                "SELECT id FROM stations WHERE code = :code AND tenant_id = :tid"
            ), {"code": table_code, "tid": tenant_id})
            station_row = st_result.fetchone()
            if not station_row:
                print(f"  SKIP job={job_id}: no station for {table_code}")
                continue
            station_id = station_row[0]

            # Get active schema
            schema_result = await db.execute(text(
                "SELECT id, unique_key_fields FROM station_schemas "
                "WHERE station_id = :sid AND is_active = true "
                "ORDER BY schema_version DESC LIMIT 1"
            ), {"sid": station_id})
            schema_row = schema_result.fetchone()
            schema_id = schema_row[0] if schema_row else None
            unique_key_fields = []
            if schema_row and schema_row[1]:
                try:
                    import json
                    ukf = schema_row[1]
                    if isinstance(ukf, str):
                        ukf = json.loads(ukf)
                    unique_key_fields = list(ukf) if ukf else []
                except Exception:
                    pass

            # Get valid staging rows for this job
            rows_result = await db.execute(text(
                "SELECT parsed_json FROM staging_rows "
                "WHERE job_id = :jid AND is_valid = true "
                "ORDER BY row_index"
            ), {"jid": job_id})
            staging_rows = rows_result.fetchall()

            migrated = 0
            for idx, (row_data,) in enumerate(staging_rows):
                if not isinstance(row_data, dict):
                    continue

                # Compute lot_no_raw
                if unique_key_fields:
                    lot_no_raw = "_".join(
                        str(row_data.get(f, "")) for f in unique_key_fields
                    ).strip("_") or str(idx)
                else:
                    lot_no_raw = str(idx)

                # Skip if already exists
                check = await db.execute(text(
                    "SELECT id FROM generic_records "
                    "WHERE tenant_id = :tid AND station_id = :sid AND lot_no_raw = :lot"
                ), {"tid": tenant_id, "sid": station_id, "lot": lot_no_raw})
                if check.fetchone():
                    continue

                # Insert
                new_id = str(uuid.uuid4())
                import json
                await db.execute(text(
                    "INSERT INTO generic_records "
                    "(id, tenant_id, station_id, schema_version_id, lot_no_raw, lot_no_norm, data, created_at, updated_at) "
                    "VALUES (:id, :tid, :sid, :schema_id, :lot_raw, :lot_norm, :data, now(), now())"
                ), {
                    "id": new_id,
                    "tid": tenant_id,
                    "sid": station_id,
                    "schema_id": schema_id,
                    "lot_raw": lot_no_raw,
                    "lot_norm": lot_no_raw.lower().replace(" ", "_"),
                    "data": json.dumps(row_data),
                })
                migrated += 1

            await db.commit()
            print(f"  job={job_id} table={table_code}: migrated {migrated} rows")
            total_migrated += migrated

        print(f"\nTotal migrated: {total_migrated} rows to generic_records")

    await engine.dispose()

asyncio.run(main())
'''

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.WarningPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, desc="", timeout=60):
    print(f"\n[{desc or cmd[:60]}]")
    chan = client.get_transport().open_session()
    chan.exec_command(cmd)
    buf = b""
    deadline = time.time() + timeout
    while not chan.exit_status_ready():
        if time.time() > deadline:
            print("[TIMEOUT]")
            break
        if chan.recv_ready():
            chunk = chan.recv(4096)
            buf += chunk
            sys.stdout.write(chunk.decode(errors="replace"))
            sys.stdout.flush()
        time.sleep(0.05)
    while chan.recv_ready():
        chunk = chan.recv(4096)
        buf += chunk
        sys.stdout.write(chunk.decode(errors="replace"))
        sys.stdout.flush()
    rc = chan.recv_exit_status()
    chan.close()
    return rc

# ── 1. Upload fixed import_v2.py ──────────────────────────────────────────────
print("\n=== Uploading fixed services/import_v2.py ===")
sftp = client.open_sftp()
remote_svc = f"{BACKEND_DIR}/app/services/import_v2.py"
sftp.put(LOCAL_SERVICE, remote_svc)
print(f"  OK -> {remote_svc}")

# ── 2. Upload migration script ────────────────────────────────────────────────
REMOTE_MIG = "/tmp/migrate_to_generic.py"
with sftp.file(REMOTE_MIG, "w") as f:
    f.write(MIGRATION_SCRIPT)
sftp.chmod(REMOTE_MIG, stat.S_IRWXU)
sftp.close()
print(f"  OK -> {REMOTE_MIG}")

# ── 3. Run migration ──────────────────────────────────────────────────────────
print("\n=== Running migration (staging_rows -> generic_records) ===")
run(f"cd {BACKEND_DIR} && {VENV} {REMOTE_MIG} 2>&1", "migration", timeout=60)

# ── 4. Restart uvicorn ────────────────────────────────────────────────────────
print("\n=== Restarting uvicorn ===")
run("pkill -f 'uvicorn app.main:app' || true", "kill uvicorn", timeout=10)
time.sleep(2)
admin_key = _require_env("VM_ADMIN_API_KEY")
start_cmd = (
    f"cd {BACKEND_DIR} && "
    f"ADMIN_API_KEYS='{admin_key}' "
    f"nohup {VENV} -m uvicorn app.main:app "
    f"--host 0.0.0.0 --port 8000 >> {LOG_FILE} 2>&1 &"
)
run(start_cmd, "start uvicorn", timeout=10)
time.sleep(3)

# ── 5. Verify ─────────────────────────────────────────────────────────────────
print("\n=== Verifying ===")
run("curl -s http://localhost:8000/healthz", "healthz", timeout=10)

# Login and test query
print("\n=== Test query after fix ===")
run(
    "API_KEY=$(curl -s -X POST http://localhost:8000/api/auth/login "
    "-H 'Content-Type: application/json' "
    "-d '{\"username\":\"manager\",\"password\":\"TestPass123!\",\"tenant_code\":\"default\"}' "
    "| python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('api_key',''))\" 2>/dev/null); "
    "curl -s -H \"X-API-Key: $API_KEY\" "
    "'http://localhost:8000/api/forms/daihui_entry/records?page=1&page_size=5' "
    "| python3 -m json.tool 2>/dev/null | grep -E '\"total\"|\"lot_no_raw\"|\"records\"' | head -10",
    "Test /api/forms/daihui_entry/records",
    timeout=20,
)

client.close()
print("\n=== Fix complete ===")
