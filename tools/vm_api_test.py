"""Comprehensive VM API endpoint tester – runs on VM via venv python3."""
import json, sys, time, random
from pathlib import Path

BASE = "http://localhost:8000"
KEY = ""
TID = ""

try:
    import requests
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ── Login ────────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/auth/login", json={
    "tenant_code": "default", "username": "manager", "password": "TestPass123!"
})
d = r.json()
KEY = d["api_key"]
TID = d["tenant_id"]
print(f"Login {r.status_code}: key={KEY[:16]}... tenant={TID}")

def H():
    return {"X-API-Key": KEY, "X-Tenant-Id": TID}

def HA():
    return {**H(), "X-Admin-API-Key": "daihui-admin-key-2026"}

results: list[tuple] = []

def test(method: str, path: str, desc: str, admin=False, **kwargs):
    url = BASE + path
    headers = HA() if admin else H()
    try:
        r = requests.request(method, url, headers=headers, timeout=20, **kwargs)
        ok = "OK" if r.status_code < 400 else ("4xx" if r.status_code < 500 else "5xx")
        results.append((ok, method, path, r.status_code, desc, r.text[:300]))
        icon = {"OK": "✅", "4xx": "⚠️", "5xx": "❌"}.get(ok, "?")
        print(f"  {icon} {r.status_code:3} {method:7} {path}")
        return r.status_code, r.text
    except Exception as e:
        results.append(("ERR", method, path, "---", desc, str(e)))
        print(f"  💥 --- {method:7} {path} → {e}")
        return "---", str(e)


# ════════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ════════════════════════════════════════════════════════════════════
print("\n╔═ 1. HEALTH CHECK ═══════════════════════════════════════╗")
test("GET", "/healthz", "Basic health")
test("GET", "/healthz/", "Basic health (trailing slash)")
test("GET", "/healthz/detailed", "Detailed health w/ DB & disk info")
test("GET", "/healthz/ready", "Readiness check")
test("GET", "/healthz/live", "Liveness check")

# ════════════════════════════════════════════════════════════════════
# 2. AUTHENTICATION
# ════════════════════════════════════════════════════════════════════
print("\n╔═ 2. AUTHENTICATION ═════════════════════════════════════╗")
test("GET", "/api/auth/whoami", "Who am I (current session)")
test("GET", "/api/auth/bootstrap-status", "Bootstrap config status")
test("GET", "/api/auth/bootstrap/manager-status", "Manager account bootstrap status")
test("GET", "/api/auth/users", "List all users in tenant")

# Create → patch → reset-pw → rebind → delete
ts = int(time.time())
code, body = test("POST", "/api/auth/users", "Create operator user",
    json={"username": f"op_{ts}", "password": "Operator123!", "role": "operator"})
user_id = None
try:
    user_id = json.loads(body).get("id")
    print(f"     created user_id={user_id}")
except Exception:
    pass

if user_id:
    test("PATCH", f"/api/auth/users/{user_id}", "Update user (set inactive)",
        json={"is_active": False})
    test("POST", f"/api/auth/users/{user_id}/password-reset", "Reset user password",
        json={"new_password": "NewPw456!"})
    test("PATCH", f"/api/auth/users/{user_id}/tenant", "Rebind user to same tenant",
        json={"tenant_id": TID})
    test("DELETE", f"/api/auth/users/{user_id}", "Delete user")

test("POST", "/api/auth/me/password", "Change my own password (same value)",
    json={"current_password": "TestPass123!", "new_password": "TestPass123!"})
test("POST", "/api/auth/admin/tenant-api-keys", "Issue a new tenant API key",
    json={"tenant_id": TID, "label": f"ci-test-{ts}"})


# ════════════════════════════════════════════════════════════════════
# 3. GENERIC FORMS
# ════════════════════════════════════════════════════════════════════
print("\n╔═ 3. GENERIC FORMS ══════════════════════════════════════╗")
test("GET", "/api/forms", "List all forms (5 daihui + others)")

# Create
test("POST", "/api/forms", "Create form 'gf_test'",
    json={"code": "gf_test", "name": "通用表單測試", "sort_order": 77})

# Set schema
test("PUT", "/api/forms/gf_test/schema", "Set form schema (4 fields)",
    json={"fields": [
        {"name": "product",  "type": "string",  "label": "品名",  "required": True,  "is_key": False},
        {"name": "serial",   "type": "string",  "label": "序號",  "required": False, "is_key": True},
        {"name": "qty",      "type": "integer", "label": "數量",  "required": False, "is_key": False},
        {"name": "weight",   "type": "decimal", "label": "重量",  "required": False, "is_key": False},
    ]})

# Upload valid CSV (3 rows)
csv_valid = "product,serial,qty,weight\nWidgetA,SN-A1,10,1.50\nWidgetB,SN-B2,20,2.00\nWidgetC,SN-C3,5,0.80"
test("POST", "/api/forms/gf_test/upload", "Upload valid CSV (3 rows, all imported)",
    files={"file": ("valid.csv", csv_valid.encode(), "text/csv")})

# Upload CSV with missing required field → errors list
csv_missing = "product,serial,qty,weight\n,SN-ERR,5,1.0"
test("POST", "/api/forms/gf_test/upload", "Upload CSV missing required 'product' → error row",
    files={"file": ("missing.csv", csv_missing.encode(), "text/csv")})

# Upload CSV with completely wrong headers → 422
csv_wrong = "ColA,ColB,ColC\ndata1,data2,data3"
test("POST", "/api/forms/gf_test/upload", "Upload CSV with mismatched headers → 422",
    files={"file": ("wrong.csv", csv_wrong.encode(), "text/csv")})

# List records (expect 3)
code, body = test("GET", "/api/forms/gf_test/records", "List records (expect 3)")
rec_id = None
try:
    recs = json.loads(body).get("records", [])
    rec_id = recs[0]["id"] if recs else None
    total = json.loads(body).get("total", 0)
    print(f"     total={total}, first_id={rec_id}")
except Exception:
    pass

# Paginate
test("GET", "/api/forms/gf_test/records?page=1&page_size=2", "List records paginated (page_size=2)")

# Delete one record
if rec_id:
    test("DELETE", f"/api/forms/gf_test/records/{rec_id}", "Delete single record by ID")
    test("GET", "/api/forms/gf_test/records", "List records after delete (expect 2)")

# Delete the form (cleanup)
test("DELETE", "/api/forms/gf_test", "Delete form + all its records")
test("GET", "/api/forms", "List forms again (gf_test should be gone)")

# Upload to bootstrap daihui form via generic endpoint
daihui_entry_csv = (
    "表單名稱,入庫日期,規格,"
    "批號,數量,總重量\n"
    "入庫單,2026-06-27,120mm,"
    f"GENERIC-{ts},25,125.5"
)
test("POST", "/api/forms/daihui_entry/upload", "Upload to daihui_entry (Chinese headers)",
    files={"file": ("daihui.csv", daihui_entry_csv.encode("utf-8"), "text/csv")})
test("GET", "/api/forms/daihui_entry/records?page_size=3", "List daihui_entry records (newest 3)")


# ════════════════════════════════════════════════════════════════════
# 4. IMPORT V2
# ════════════════════════════════════════════════════════════════════
print("\n╔═ 4. IMPORT V2 ══════════════════════════════════════════╗")

uid = random.randint(1000, 9999)
csv_daihui = (
    "表單名稱,入庫日期,規格,"
    "批號,數量,總重量\n"
    f"入庫單,2026-06-27,90mm,V2-{uid},30,150.0"
)

code, body = test("POST", "/api/v2/import/jobs", "Create import job (fingerprint auto-detect)",
    files={"files": ("entry.csv", csv_daihui.encode("utf-8"), "text/csv")})
job_id = None
try:
    jd = json.loads(body)
    job_id = jd.get("id")
    print(f"     job_id={job_id}  table_code={jd.get('table_code')}  status={jd.get('status')}")
except Exception:
    pass

time.sleep(1)

if job_id:
    test("GET", f"/api/v2/import/jobs/{job_id}", "Get job (expect READY after auto-validate)")
    test("GET", f"/api/v2/import/jobs/{job_id}/errors", "Get job errors (expect empty)")
    code, body = test("POST", f"/api/v2/import/jobs/{job_id}/commit", "Commit import job")
    try:
        print(f"     commit table_code={json.loads(body).get('table_code')} status={json.loads(body).get('status')}")
    except Exception:
        pass
    time.sleep(2)
    code, body = test("GET", f"/api/v2/import/jobs/{job_id}", "Get job (expect COMPLETED)")
    try:
        jf = json.loads(body)
        print(f"     final status={jf.get('status')} rows={jf.get('total_rows')} table_code={jf.get('table_code')}")
    except Exception:
        pass

# Cancel test
uid2 = random.randint(1000, 9999)
csv_cancel = (
    "表單名稱,入庫日期,規格,"
    "批號,數量,總重量\n"
    f"入庫單,2026-06-27,100mm,CANCEL-{uid2},5,25.0"
)
code2, body2 = test("POST", "/api/v2/import/jobs", "Create job to cancel",
    files={"files": ("cancel.csv", csv_cancel.encode("utf-8"), "text/csv")})
cancel_id = None
try:
    cancel_id = json.loads(body2).get("id")
except Exception:
    pass
time.sleep(0.5)
if cancel_id:
    test("POST", f"/api/v2/import/jobs/{cancel_id}/cancel", "Cancel import job (UPLOADED→CANCELLED)")
    code3, body3 = test("GET", f"/api/v2/import/jobs/{cancel_id}", "Verify cancelled status")
    try:
        print(f"     status={json.loads(body3).get('status')}")
    except Exception:
        pass

# from-upload-job with fake ID → expect 404/422
test("POST", "/api/v2/import/jobs/from-upload-job",
    "from-upload-job with nonexistent upload_job_id → error",
    json={"upload_job_id": "00000000-0000-0000-0000-000000000000"})


# ════════════════════════════════════════════════════════════════════
# 5. TENANTS
# ════════════════════════════════════════════════════════════════════
print("\n╔═ 5. TENANTS ════════════════════════════════════════════╗")
test("GET", "/api/tenants", "List tenants (current user's)")

# Create tenant
code, body = test("POST", "/api/tenants", "Create tenant",
    json={"code": f"ten{ts}", "name": "API建立的租戶"})
new_tid = None
try:
    new_tid = json.loads(body).get("id")
    print(f"     new tenant_id={new_tid}")
except Exception:
    pass

if new_tid:
    test("PATCH", f"/api/tenants/{new_tid}", "Update tenant name",
        json={"name": "API建立的租戶（已更新）"})
    test("DELETE", f"/api/tenants/{new_tid}", "Delete tenant")

# Admin create tenant (needs X-Admin-API-Key)
test("POST", "/api/tenants/admin", "Admin create tenant (X-Admin-API-Key)",
    admin=True,
    json={"code": f"adm{ts}", "name": "Admin建立的租戶"})


# ════════════════════════════════════════════════════════════════════
# 6. LEGACY UPLOAD
# ════════════════════════════════════════════════════════════════════
print("\n╔═ 6. LEGACY UPLOAD ══════════════════════════════════════╗")
csv_bytes = csv_valid.encode()

test("POST", "/api/upload", "Legacy upload endpoint (expect deprecation hint)",
    files={"file": ("legacy.csv", csv_bytes, "text/csv")})
test("GET", "/api/upload/pdf/service-status", "PDF conversion service status")
# PDF upload with dummy bytes – endpoint should reject or error gracefully
test("POST", "/api/upload/pdf", "PDF upload (dummy bytes, expect error)",
    files={"file": ("dummy.pdf", b"%PDF-1.4 dummy", "application/pdf")})
# Status endpoints with fake IDs
fake_id = "00000000-0000-0000-0000-000000000001"
test("GET",  f"/api/upload/{fake_id}/status", "Upload job status (fake id → 404)")
test("GET",  f"/api/upload/{fake_id}/edits",  "Upload job edits  (fake id → 404)")
test("POST", f"/api/upload/{fake_id}/validate", "Re-validate upload (fake id → 404)")
test("PUT",  f"/api/upload/{fake_id}/content", "Save edits (fake id → 404)",
    json={"rows": []})
# PDF convert status with fake id
test("GET",  f"/api/upload/pdf/{fake_id}/convert/status",  "PDF convert status  (fake → 404)")
test("GET",  f"/api/upload/pdf/{fake_id}/convert/outputs", "PDF convert outputs (fake → 404)")
test("POST", f"/api/upload/pdf/{fake_id}/convert",        "PDF convert trigger (fake → 404)")
test("POST", f"/api/upload/pdf/{fake_id}/convert/ingest", "PDF convert ingest  (fake → 404)")


# ════════════════════════════════════════════════════════════════════
# 7. LEGACY IMPORT
# ════════════════════════════════════════════════════════════════════
print("\n╔═ 7. LEGACY IMPORT ══════════════════════════════════════╗")
test("POST", "/api/import", "Legacy /api/import (expect deprecation or 405)",
    json={})


# ════════════════════════════════════════════════════════════════════
# 8. VALIDATE
# ════════════════════════════════════════════════════════════════════
print("\n╔═ 8. VALIDATE ═══════════════════════════════════════════╗")
test("GET", "/api/validate", "Validate results (no filter)")
test("GET", "/api/validate?form_code=daihui_entry", "Validate results for daihui_entry")
test("GET", "/api/validate?form_code=nonexistent", "Validate results for nonexistent form")


# ════════════════════════════════════════════════════════════════════
# SUMMARY TABLE
# ════════════════════════════════════════════════════════════════════
print("\n")
print("=" * 115)
print(f"  {'St':3} {'Method':7} {'Path':65} {'Code':4}  Description")
print("=" * 115)
icons = {"OK": "✅", "4xx": "⚠️", "5xx": "❌", "ERR": "💥"}
for ok, m, p, c, desc, body in results:
    icon = icons.get(ok, "?")
    print(f"  {icon} {m:7} {p:65} {c!s:4}  {desc}")

total = len(results)
n_ok  = sum(1 for r in results if r[0] == "OK")
n_4xx = sum(1 for r in results if r[0] == "4xx")
n_5xx = sum(1 for r in results if r[0] == "5xx")
n_err = sum(1 for r in results if r[0] == "ERR")
print("=" * 115)
print(f"  Total {total} | ✅ PASS {n_ok} | ⚠️ 4xx {n_4xx} | ❌ 5xx {n_5xx} | 💥 ERR {n_err}")

print("\n╔═ FAILURES / WARNINGS DETAIL ════════════════════════════╗")
for ok, m, p, c, desc, body in results:
    if ok in ("5xx", "ERR"):
        print(f"\n  ❌ [{ok}] {m} {p} → {c}")
        print(f"     {body[:400]}")
for ok, m, p, c, desc, body in results:
    if ok == "4xx":
        print(f"\n  ⚠️  [4xx] {m} {p} → {c}: {body[:200]}")
