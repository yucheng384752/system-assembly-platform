"""Final targeted tests for remaining endpoint issues."""
import json, time
import requests as req

BASE = "http://localhost:8000"
ADMIN_KEY = "vm-admin-key-2026"

r = req.post(f"{BASE}/api/auth/login", json={"tenant_code": "default", "username": "manager", "password": "TestPass123!"})
d = r.json()
KEY = d["api_key"]
TID = d["tenant_id"]

def H():  return {"X-API-Key": KEY, "X-Tenant-Id": TID}
def HA(): return {**H(), "X-Admin-API-Key": ADMIN_KEY}

def show(code, desc, body=""):
    icon = "OK " if code < 400 else ("WRN" if code < 500 else "ERR")
    print(f"  [{icon}] {code} {desc}")
    if body and code >= 400:
        print(f"        {body[:200]}")

ts = int(time.time())

# ── 1. User lifecycle: create → password-reset → rebind → delete ─────
print("\n[1] Full user lifecycle")
r1 = req.post(f"{BASE}/api/auth/users", headers=H(),
    json={"username": f"lc{ts}", "password": "Lc1234!", "role": "user"})
show(r1.status_code, f"POST /api/auth/users")
uid = r1.json().get("id") if r1.status_code == 201 else None

if uid:
    r2 = req.post(f"{BASE}/api/auth/users/{uid}/password-reset", headers=H(),
        json={"new_password": "LcNew456!"})
    show(r2.status_code, f"POST /api/auth/users/.../password-reset", r2.text)

    r3 = req.patch(f"{BASE}/api/auth/users/{uid}/tenant", headers=HA(),
        json={"tenant_id": TID})
    show(r3.status_code, f"PATCH /api/auth/users/.../tenant (admin key)", r3.text)

    r4 = req.delete(f"{BASE}/api/auth/users/{uid}", headers=H())
    show(r4.status_code, f"DELETE /api/auth/users/...")

# ── 2. Change my own password (different value) ───────────────────────
print("\n[2] Change my password")
r5 = req.post(f"{BASE}/api/auth/me/password", headers=H(),
    json={"old_password": "TestPass123!", "new_password": "TempPw999!"})
show(r5.status_code, "POST /api/auth/me/password (old → new different)", r5.text)

# Re-login, then restore
if r5.status_code == 204:
    r6 = req.post(f"{BASE}/api/auth/login",
        json={"tenant_code": "default", "username": "manager", "password": "TempPw999!"})
    show(r6.status_code, "Login with new password TempPw999!")
    KEY2 = r6.json().get("api_key", KEY)
    def H2(): return {"X-API-Key": KEY2, "X-Tenant-Id": TID}
    r7 = req.post(f"{BASE}/api/auth/me/password", headers=H2(),
        json={"old_password": "TempPw999!", "new_password": "TestPass123!"})
    show(r7.status_code, "POST /api/auth/me/password (restore TestPass123!)", r7.text)

# ── 3. Tenant full CRUD ───────────────────────────────────────────────
print("\n[3] Tenant CRUD")
ts2 = ts + 7
r8 = req.post(f"{BASE}/api/tenants", headers=HA(),
    json={"code": f"tc{ts2}", "name": "Test Tenant CRUD"})
show(r8.status_code, "POST /api/tenants (admin)", r8.text)
ntid = r8.json().get("id") if r8.status_code == 201 else None

if ntid:
    r9 = req.patch(f"{BASE}/api/tenants/{ntid}", headers=HA(),
        json={"name": "Test Tenant CRUD (Updated)"})
    show(r9.status_code, f"PATCH /api/tenants/{ntid[:8]}...", r9.text)

    r10 = req.delete(f"{BASE}/api/tenants/{ntid}", headers=HA())
    show(r10.status_code, f"DELETE /api/tenants/{ntid[:8]}...", r10.text)

# ── 4. from-upload-job with legacy upload process_id ─────────────────
print("\n[4] V2 import from-upload-job")
csv_content = b"product,serial\nItemA,SN001\nItemB,SN002"
rU = req.post(f"{BASE}/api/upload", headers=H(),
    files={"file": ("test_fuj.csv", csv_content, "text/csv")})
show(rU.status_code, "POST /api/upload (get process_id)")
proc_id = rU.json().get("process_id") if rU.status_code == 200 else None
print(f"  process_id = {proc_id}")

if proc_id:
    rFUJ = req.post(f"{BASE}/api/v2/import/jobs/from-upload-job", headers=H(),
        json={"upload_process_id": proc_id})
    show(rFUJ.status_code, "POST /api/v2/import/jobs/from-upload-job (real process_id)", rFUJ.text)

# ── 5. Confirm PDF endpoints ──────────────────────────────────────────
print("\n[5] PDF endpoints")
rPDF_status = req.get(f"{BASE}/api/upload/pdf/service-status", headers=H())
show(rPDF_status.status_code, "GET /api/upload/pdf/service-status")
print(f"  {rPDF_status.text[:150]}")

# Upload a valid-looking PDF (dummy bytes still, check endpoint response)
pdf_bytes = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<</Size 1>>\nstartxref\n9\n%%EOF"
rPDFup = req.post(f"{BASE}/api/upload/pdf", headers=H(),
    files={"file": ("test.pdf", pdf_bytes, "application/pdf")})
show(rPDFup.status_code, "POST /api/upload/pdf (minimal PDF)")
print(f"  {rPDFup.text[:150]}")

print("\n=== ALL DONE ===")
