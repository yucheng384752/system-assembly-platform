"""Re-test endpoints that failed due to wrong parameters in first pass."""
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

results: list = []

def t(m, p, desc, admin=False, **kw):
    headers = HA() if admin else H()
    try:
        r = req.request(m, BASE+p, headers=headers, timeout=20, **kw)
        ok = "PASS" if r.status_code < 400 else ("4xx" if r.status_code < 500 else "5xx")
        results.append((ok, m, p, r.status_code, desc, r.text[:300]))
        icon = {"PASS": "OK ", "4xx": "WRN", "5xx": "ERR"}.get(ok, "?  ")
        print(f"  [{icon}] {r.status_code} {m} {p}")
        return r.status_code, r.text
    except Exception as e:
        results.append(("ERR", m, p, "---", desc, str(e)))
        print(f"  [ERR] --- {m} {p} => {e}")
        return "---", str(e)

ts = int(time.time())

# ── Auth: Create user (valid roles: "manager" | "user") ──────────────
print("\n[FIX] Auth endpoints")
code, body = t("POST", "/api/auth/users", "Create user (role=user)",
    json={"username": f"u{ts}", "password": "User1234!", "role": "user"})
uid = None
try:
    uid = json.loads(body).get("id")
    print(f"   user_id={uid}")
except Exception: pass

if uid:
    t("PATCH",  f"/api/auth/users/{uid}", "Patch user (deactivate)", json={"is_active": False})
    t("POST",   f"/api/auth/users/{uid}/password-reset", "Reset user password", json={"new_password": "NewPw789!"})
    t("PATCH",  f"/api/auth/users/{uid}/tenant", "Rebind user tenant", json={"tenant_id": TID})
    t("DELETE", f"/api/auth/users/{uid}", "Delete user")

# Change password: correct field name is old_password
t("POST", "/api/auth/me/password", "Change password (old_password field)",
    json={"old_password": "TestPass123!", "new_password": "TestPass123!"})

# Admin-key required endpoints
t("GET",  "/api/auth/bootstrap/manager-status", "Manager bootstrap status (admin)", admin=True)
t("POST", "/api/auth/admin/tenant-api-keys", "Issue API key (admin)",
    admin=True, json={"tenant_id": TID, "label": f"fix-key-{ts}"})

# ── Tenants: require admin key ────────────────────────────────────────
print("\n[FIX] Tenant endpoints (admin key)")
code, body = t("POST", "/api/tenants", "Create tenant (admin)", admin=True,
    json={"code": f"fixt{ts}", "name": "Fix Tenant"})
new_tid = None
try: new_tid = json.loads(body).get("id")
except Exception: pass

if new_tid:
    t("PATCH",  f"/api/tenants/{new_tid}", "Update tenant", admin=True, json={"name": "Fix Tenant Updated"})
    t("DELETE", f"/api/tenants/{new_tid}", "Delete tenant", admin=True)

t("POST", "/api/tenants/admin", "Admin create tenant", admin=True,
    json={"code": f"adm{ts}", "name": "Admin Tenant"})

# ── Legacy Upload: get a real process_id first ────────────────────────
print("\n[FIX] Legacy upload with real process_id")
csv_data = "product,serial,qty,weight\nItem1,S001,10,1.5\nItem2,S002,5,0.8"
files = {"file": ("data.csv", csv_data.encode(), "text/csv")}
code, body = t("POST", "/api/upload", "Legacy upload (create process)", files=files)
print(f"   Legacy upload body: {body[:300]}")
proc_id = None
try:
    bd = json.loads(body)
    proc_id = bd.get("process_id") or bd.get("id") or bd.get("upload_id")
    print(f"   proc_id = {proc_id}")
except Exception: pass

if proc_id:
    t("GET",  f"/api/upload/{proc_id}/status",   "Upload status (real process_id)")
    t("GET",  f"/api/upload/{proc_id}/edits",    "Upload edits (real process_id)")
    t("POST", f"/api/upload/{proc_id}/validate", "Validate upload (real process_id)")
    t("GET",  "/api/validate", "Validate results (with process_id)",
        params={"process_id": proc_id})
    t("PUT",  f"/api/upload/{proc_id}/content", "Save edits with csv_text",
        json={"csv_text": csv_data})
    t("POST", "/api/import", "Legacy import with process_id",
        json={"process_id": proc_id})

# from-upload-job: field is upload_process_id
t("POST", "/api/v2/import/jobs/from-upload-job",
    "from-upload-job (upload_process_id field)",
    json={"upload_process_id": "00000000-0000-0000-0000-000000000000"})

# ── Summary ───────────────────────────────────────────────────────────
print()
print("=" * 105)
print(f"  St   Method  Path{' '*55}Code  Description")
print("=" * 105)
for ok, m, p, c, desc, body in results:
    icon = {"PASS": "OK ", "4xx": "WRN", "5xx": "ERR"}.get(ok, "ERR")
    print(f"  {icon}  {m:7} {p:60} {c!s:4}  {desc}")

n_ok = sum(1 for r in results if r[0] == "PASS")
n_4  = sum(1 for r in results if r[0] == "4xx")
n_5  = sum(1 for r in results if r[0] == "5xx")
print(f"\n  Total {len(results)} | PASS {n_ok} | 4xx {n_4} | 5xx {n_5}")

print("\n[DETAIL: non-PASS]")
for ok, m, p, c, desc, body in results:
    if ok != "PASS":
        print(f"\n  [{ok}] {m} {p} -> {c}")
        print(f"   {body[:400]}")
