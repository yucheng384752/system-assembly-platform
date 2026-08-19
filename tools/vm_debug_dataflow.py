"""Debug script: trace full data flow for V2 import and generic forms upload."""
import requests as req
import json, time, random

BASE = "http://localhost:8000"

# 1. Login
r = req.post(f"{BASE}/api/auth/login",
    json={"tenant_code": "default", "username": "manager", "password": "TestPass123!"})
d = r.json()
KEY = d["api_key"]
TID = d["tenant_id"]
print(f"[1] Login {r.status_code}: key={KEY[:16]}...")

H = {"X-API-Key": KEY, "X-Tenant-Id": TID}

# ═══════════════════════════════════════════════════════════
# PATH A: V2 Import (daihui_entry)
# ═══════════════════════════════════════════════════════════
print("\n=== PATH A: V2 Import /api/v2/import/jobs ===")
uid = random.randint(1000, 9999)
csv_entry = (
    "表單名稱,入庫日期,規格,批號,數量,總重量\n"
    f"入庫單,2026-06-27,100mm,DBG-{uid},10,50.0\n"
)

# A1. Create job
r = req.post(f"{BASE}/api/v2/import/jobs", headers=H,
    files={"files": ("entry.csv", csv_entry.encode("utf-8"), "text/csv")})
print(f"[A1] POST /api/v2/import/jobs -> {r.status_code}")
if r.status_code != 201:
    print(f"     FAIL: {r.text[:300]}")
    job_id = None
else:
    jd = r.json()
    job_id = jd["id"]
    print(f"     job_id={job_id}")
    print(f"     table_code={jd.get('table_code')}")
    print(f"     status={jd.get('status')}")

time.sleep(1)

# A2. Get job status (should be READY after auto-validation)
if job_id:
    r = req.get(f"{BASE}/api/v2/import/jobs/{job_id}", headers=H)
    jd2 = r.json()
    print(f"\n[A2] GET job -> status={jd2.get('status')} total_rows={jd2.get('total_rows')} error_count={jd2.get('error_count')}")

    # A3. Commit
    r = req.post(f"{BASE}/api/v2/import/jobs/{job_id}/commit", headers=H)
    jd3 = r.json()
    print(f"\n[A3] POST commit -> {r.status_code} status={jd3.get('status')}")

    time.sleep(2)

    # A4. Final status
    r = req.get(f"{BASE}/api/v2/import/jobs/{job_id}", headers=H)
    jd4 = r.json()
    print(f"\n[A4] Final status={jd4.get('status')} total_rows={jd4.get('total_rows')} error_count={jd4.get('error_count')}")
    if jd4.get("error_summary"):
        print(f"     error_summary={jd4.get('error_summary')}")

    # A5. Errors
    r = req.get(f"{BASE}/api/v2/import/jobs/{job_id}/errors", headers=H)
    errors = r.json()
    print(f"\n[A5] Errors: {len(errors) if isinstance(errors, list) else errors}")
    if isinstance(errors, list) and errors:
        for e in errors[:3]:
            print(f"     {e}")

# A6. Check DB row count
import subprocess, os
env = os.environ.copy()
env["PGPASSWORD"] = "qqq123"
result = subprocess.run(
    ["psql", "-h", "127.0.0.1", "-U", "form_system", "-d", "form_system",
     "-c", "SELECT COUNT(*) FROM daihui_entry;"],
    capture_output=True, text=True, env=env, timeout=10
)
print(f"\n[A6] daihui_entry count: {result.stdout.strip()}")

# ═══════════════════════════════════════════════════════════
# PATH B: Generic Forms Upload
# ═══════════════════════════════════════════════════════════
print("\n=== PATH B: Generic Forms /api/forms/{code}/upload ===")
uid2 = random.randint(1000, 9999)
csv_generic = f"product,serial,qty,weight\nTestItem,SN-{uid2},5,1.5\n"

# B1. Create form
r = req.post(f"{BASE}/api/forms", headers=H,
    json={"code": f"dbg_{uid2}", "name": "Debug Form", "sort_order": 99})
form_code = f"dbg_{uid2}"
print(f"[B1] POST /api/forms -> {r.status_code}: {form_code}")

# B2. Set schema
r = req.put(f"{BASE}/api/forms/{form_code}/schema", headers=H,
    json={"fields": [
        {"name": "product", "type": "string", "required": True, "is_key": False, "label": "品名"},
        {"name": "serial",  "type": "string", "required": False, "is_key": True,  "label": "序號"},
        {"name": "qty",     "type": "integer", "required": False, "is_key": False, "label": "數量"},
        {"name": "weight",  "type": "decimal", "required": False, "is_key": False, "label": "重量"},
    ]})
print(f"[B2] PUT schema -> {r.status_code}")

# B3. Upload
r = req.post(f"{BASE}/api/forms/{form_code}/upload", headers=H,
    files={"file": ("data.csv", csv_generic.encode("utf-8"), "text/csv")})
print(f"[B3] POST upload -> {r.status_code}")
upload_result = r.json() if r.status_code in (200, 201) else {}
print(f"     imported={upload_result.get('imported')} skipped={upload_result.get('skipped')} errors={upload_result.get('errors')}")

# B4. Query records
r = req.get(f"{BASE}/api/forms/{form_code}/records", headers=H)
records = r.json() if r.status_code == 200 else {}
total = records.get("total", 0)
recs = records.get("records", [])
print(f"\n[B4] GET records -> total={total}")
for rec in recs[:3]:
    print(f"     id={rec.get('id', '')[:8]}... data={rec.get('data')}")

# B5. DB count
result2 = subprocess.run(
    ["psql", "-h", "127.0.0.1", "-U", "form_system", "-d", "form_system",
     "-c", "SELECT COUNT(*) FROM generic_records;"],
    capture_output=True, text=True, env=env, timeout=10
)
print(f"\n[B5] generic_records count: {result2.stdout.strip()}")

# Cleanup
req.delete(f"{BASE}/api/forms/{form_code}", headers=H)
print(f"\n[Cleanup] Deleted {form_code}")
