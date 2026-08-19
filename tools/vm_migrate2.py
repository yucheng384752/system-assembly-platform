"""Upload and run fixed migration: staging_rows -> generic_records."""
import paramiko, stat, time, sys

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
DEPLOY_DIR = "/home/gslab/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26"
BACKEND_DIR = f"{DEPLOY_DIR}/system/backend"
VENV = f"{DEPLOY_DIR}/system/.venv/bin/python"

MIGRATION_SCRIPT = r'''
"""Migrate staging_rows -> generic_records (fixed: version col, bigint lot_no_norm)."""
import asyncio, sys, uuid, json, os
sys.path.insert(0, ".")
os.environ.setdefault("ENV_FILE",
    "/home/gslab/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26/system/.env")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.core.config import get_settings

def lot_no_norm(raw: str) -> int:
    digits = "".join(c for c in str(raw) if c.isdigit())
    return int(digits) if digits else 0

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

            # Get active schema (use 'version' not 'schema_version')
            schema_result = await db.execute(text(
                "SELECT id, unique_key_fields FROM station_schemas "
                "WHERE station_id = :sid AND is_active = true "
                "ORDER BY version DESC LIMIT 1"
            ), {"sid": station_id})
            schema_row = schema_result.fetchone()
            schema_id = schema_row[0] if schema_row else None
            unique_key_fields = []
            if schema_row and schema_row[1]:
                try:
                    ukf = schema_row[1]
                    if isinstance(ukf, str):
                        ukf = json.loads(ukf)
                    unique_key_fields = list(ukf) if ukf else []
                except Exception:
                    pass

            # Get valid staging rows
            rows_result = await db.execute(text(
                "SELECT parsed_json FROM staging_rows "
                "WHERE job_id = :jid AND is_valid = true "
                "ORDER BY row_index"
            ), {"jid": job_id})
            staging_rows = rows_result.fetchall()

            migrated = 0
            skipped = 0
            for idx, (row_data,) in enumerate(staging_rows):
                if not isinstance(row_data, dict):
                    continue

                # Compute lot_no_raw
                if unique_key_fields:
                    lot_raw = "_".join(
                        str(row_data.get(f, "")) for f in unique_key_fields
                    ).strip("_") or str(idx)
                else:
                    lot_raw = str(idx)
                lot_norm = lot_no_norm(lot_raw)

                # Skip if already exists
                check = await db.execute(text(
                    "SELECT id FROM generic_records "
                    "WHERE tenant_id = :tid AND station_id = :sid AND lot_no_raw = :lot"
                ), {"tid": tenant_id, "sid": station_id, "lot": lot_raw})
                if check.fetchone():
                    skipped += 1
                    continue

                # Insert (lot_no_raw max 50 chars)
                new_id = str(uuid.uuid4())
                await db.execute(text(
                    "INSERT INTO generic_records "
                    "(id, tenant_id, station_id, schema_version_id, lot_no_raw, lot_no_norm, data, created_at, updated_at) "
                    "VALUES (:id, :tid, :sid, :schema_id, :lot_raw, :lot_norm, :data, now(), now())"
                ), {
                    "id": new_id,
                    "tid": tenant_id,
                    "sid": station_id,
                    "schema_id": schema_id,
                    "lot_raw": lot_raw[:50],
                    "lot_norm": lot_norm,
                    "data": json.dumps(row_data),
                })
                migrated += 1

            await db.commit()
            print(f"  job={str(job_id)[:8]}... table={table_code}: migrated={migrated}, skipped={skipped}")
            total_migrated += migrated

        print(f"\nDone: {total_migrated} rows written to generic_records")

    await engine.dispose()

asyncio.run(main())
'''

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, desc="", timeout=60):
    print(f"\n[{desc}]"); print("-"*60)
    chan = client.get_transport().open_session()
    chan.exec_command(cmd)
    buf = b""
    deadline = time.time() + timeout
    while not chan.exit_status_ready():
        if time.time() > deadline: print("[TIMEOUT]"); break
        if chan.recv_ready():
            chunk = chan.recv(4096); buf += chunk
            sys.stdout.write(chunk.decode(errors="replace")); sys.stdout.flush()
        time.sleep(0.05)
    while chan.recv_ready():
        chunk = chan.recv(4096); buf += chunk
        sys.stdout.write(chunk.decode(errors="replace")); sys.stdout.flush()
    chan.recv_exit_status(); chan.close()

# Upload migration script
REMOTE = "/tmp/migrate2.py"
sftp = client.open_sftp()
with sftp.file(REMOTE, "w") as f:
    f.write(MIGRATION_SCRIPT)
sftp.chmod(REMOTE, stat.S_IRWXU)
sftp.close()
print(f"Uploaded {REMOTE}")

# Run migration
run(f"cd {BACKEND_DIR} && {VENV} {REMOTE} 2>&1", "migration", timeout=60)

# Verify
run(
    "API_KEY=$(curl -s -X POST http://localhost:8000/api/auth/login "
    "-H 'Content-Type: application/json' "
    "-d '{\"username\":\"manager\",\"password\":\"TestPass123!\",\"tenant_code\":\"default\"}' "
    "| python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('api_key',''))\" 2>/dev/null); "
    "curl -s -H \"X-API-Key: $API_KEY\" "
    "'http://localhost:8000/api/forms/daihui_entry/records?page=1&page_size=5' "
    "| python3 -m json.tool 2>/dev/null | grep -E 'total|lot_no_raw' | head -10",
    "Verify /api/forms/daihui_entry/records",
    timeout=20,
)

client.close()
print("\n=== Migration complete ===")
