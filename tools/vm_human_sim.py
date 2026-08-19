"""
Human operations simulation — runs on VM via python3.
Simulates a factory operator using the form system end-to-end.
"""
import io, json, time
import requests as req

BASE = "http://localhost:8000"
ADMIN_KEY = "vm-admin-key-2026"
results: list = []
state: dict = {}


def H(k=None):
    return {"X-API-Key": k or state.get("mgr_key", "")}


def log(step: int, label: str, ok: bool, code, body: str = ""):
    tag = "PASS" if ok else "FAIL"
    results.append((tag, step, label, code, body))
    icon = "✓" if ok else "✗"
    print(f"  [{icon}] Step {step:2d}: {label} (HTTP {code})")
    if not ok and body:
        print(f"           {body[:400]}")


# ══════════════════════════════════════════════════════════
# Phase 1: Login & Identity
# ══════════════════════════════════════════════════════════
print("\n╔═ Phase 1: Login & Identity ════════════════════════╗")

r = req.post(f"{BASE}/api/auth/login",
    json={"tenant_code": "default", "username": "manager", "password": "TestPass123!"})
ok = r.status_code == 200 and "api_key" in r.json()
if ok:
    state["mgr_key"] = r.json()["api_key"]
    state["tenant_id"] = r.json()["tenant_id"]
log(1, "POST /api/auth/login (manager)", ok, r.status_code, r.text)

r = req.get(f"{BASE}/api/auth/whoami", headers=H())
ok = r.status_code == 200 and "username" in r.json()
log(2, "GET /api/auth/whoami → confirm session identity", ok, r.status_code, r.text[:200])

r = req.get(f"{BASE}/api/auth/users", headers=H())
users = r.json() if r.status_code == 200 else []
log(3, f"GET /api/auth/users → count={len(users) if isinstance(users, list) else '?'}", r.status_code == 200, r.status_code, r.text[:200])

# ══════════════════════════════════════════════════════════
# Phase 2: Create Operator User
# ══════════════════════════════════════════════════════════
print("\n╔═ Phase 2: Create Operator Account ══════════════════╗")
ts = int(time.time())
op_name = f"op_sim_{ts}"

r = req.post(f"{BASE}/api/auth/users", headers=H(),
    json={"username": op_name, "password": "OpSim123!", "role": "user"})
ok = r.status_code in (200, 201)
if ok:
    state["op_user_id"] = r.json().get("id")
log(4, f"POST /api/auth/users → create operator '{op_name}'", ok, r.status_code, r.text[:200])

r = req.post(f"{BASE}/api/auth/login",
    json={"tenant_code": "default", "username": op_name, "password": "OpSim123!"})
ok = r.status_code == 200 and "api_key" in r.json()
if ok:
    state["op_key"] = r.json()["api_key"]
log(5, f"POST /api/auth/login (operator '{op_name}') → get api_key", ok, r.status_code, r.text[:200])

# ══════════════════════════════════════════════════════════
# Phase 3: Create Form (DB Creation)
# ══════════════════════════════════════════════════════════
print("\n╔═ Phase 3: Create Form / DB Setup ═══════════════════╗")

r = req.get(f"{BASE}/api/forms", headers=H())
forms_before = r.json() if r.status_code == 200 else []
form_codes = [f.get("code") for f in forms_before] if isinstance(forms_before, list) else []
log(6, f"GET /api/forms → {len(form_codes)} forms: {form_codes[:5]}", r.status_code == 200, r.status_code, r.text[:300])

r = req.post(f"{BASE}/api/forms", headers=H(),
    json={"code": "sim_form", "name": "模擬測試表單", "sort_order": 99})
ok = r.status_code in (200, 201, 409)  # 409 = already exists (idempotent)
log(7, "POST /api/forms → create 'sim_form'", ok, r.status_code, r.text[:200])

schema_body = {"fields": [
    {"name": "product",  "type": "string",  "required": True,  "is_key": False, "label": "品名"},
    {"name": "batch",    "type": "string",  "required": False, "is_key": True,  "label": "批號"},
    {"name": "qty",      "type": "integer", "required": False, "is_key": False, "label": "數量"},
    {"name": "note",     "type": "string",  "required": False, "is_key": False, "label": "備註"},
]}
r = req.put(f"{BASE}/api/forms/sim_form/schema", headers=H(), json=schema_body)
log(8, "PUT /api/forms/sim_form/schema → 4 fields", r.status_code in (200, 201), r.status_code, r.text[:200])

# ══════════════════════════════════════════════════════════
# Phase 4: CSV Upload (valid + error scenarios)
# ══════════════════════════════════════════════════════════
print("\n╔═ Phase 4: CSV Upload Tests ══════════════════════════╗")

csv_valid = "product,batch,qty,note\n鋼棒A,BATCH-001,100,正常品\n鋼棒B,BATCH-002,50,待確認\n鋼棒C,BATCH-003,200,已驗收\n"
r = req.post(f"{BASE}/api/forms/sim_form/upload",
    headers={"X-API-Key": state.get("mgr_key", "")},
    files={"file": ("data.csv", io.BytesIO(csv_valid.encode("utf-8")), "text/csv")})
ok = r.status_code in (200, 201)
imported = r.json().get("imported", -1) if ok else -1
ok = ok and imported == 3
log(9, f"POST /api/forms/sim_form/upload (3 valid rows) → imported={imported}", ok, r.status_code, r.text)

csv_missing = "product,batch,qty,note\n,BATCH-ERR,10,缺少品名\n"
r = req.post(f"{BASE}/api/forms/sim_form/upload",
    headers={"X-API-Key": state.get("mgr_key", "")},
    files={"file": ("missing.csv", io.BytesIO(csv_missing.encode("utf-8")), "text/csv")})
ok = r.status_code in (200, 201)
imported2 = r.json().get("imported", -1) if ok else -1
errors2 = r.json().get("errors", []) if ok else []
ok = ok and imported2 == 0 and len(errors2) > 0
log(10, f"POST upload (missing required) → imported={imported2}, errors={len(errors2)}", ok, r.status_code, r.text)

csv_wrong = "WrongCol1,WrongCol2\ndata1,data2\n"
r = req.post(f"{BASE}/api/forms/sim_form/upload",
    headers={"X-API-Key": state.get("mgr_key", "")},
    files={"file": ("wrong.csv", io.BytesIO(csv_wrong.encode("utf-8")), "text/csv")})
log(11, "POST upload (wrong headers) → expect 422", r.status_code == 422, r.status_code, r.text[:200])

# ══════════════════════════════════════════════════════════
# Phase 5: Query Records
# ══════════════════════════════════════════════════════════
print("\n╔═ Phase 5: Query Records ═════════════════════════════╗")

r = req.get(f"{BASE}/api/forms/sim_form/records?page_size=10", headers=H())
ok = r.status_code == 200
data = r.json() if ok else {}
records = data.get("records", data.get("items", []))
total = data.get("total", len(records) if isinstance(records, list) else 0)
state["first_rec_id"] = records[0]["id"] if records else None
log(12, f"GET /api/forms/sim_form/records → total={total}", ok and total == 3, r.status_code, r.text[:300])

r = req.get(f"{BASE}/api/forms/sim_form/records?page=1&page_size=2", headers=H())
ok = r.status_code == 200
data2 = r.json() if ok else {}
recs2 = data2.get("records", data2.get("items", []))
log(13, f"GET records?page_size=2 → returned {len(recs2)} rows", ok and len(recs2) == 2, r.status_code, r.text[:200])

# ══════════════════════════════════════════════════════════
# Phase 6: Import V2 — daihui_entry fingerprint flow
# ══════════════════════════════════════════════════════════
print("\n╔═ Phase 6: Import V2 (daihui fingerprint) ═══════════╗")

csv_entry = (
    "表單名稱,入庫日期,規格,批號,數量,總重量\n"
    f"入庫單,2026-06-27,100mm,SIM-{ts},50,250.0\n"
)
r = req.post(f"{BASE}/api/v2/import/jobs",
    headers={"X-API-Key": state.get("mgr_key", "")},
    files={"files": ("entry.csv", io.BytesIO(csv_entry.encode("utf-8")), "text/csv")})
ok = r.status_code == 201
job_id = r.json().get("id") if ok else None
table_code = r.json().get("table_code") if ok else None
log(14, f"POST /api/v2/import/jobs → table_code={table_code}, job_id={job_id[:8] + '...' if job_id else None}", ok, r.status_code, r.text[:300])

time.sleep(1)
if job_id:
    r = req.get(f"{BASE}/api/v2/import/jobs/{job_id}", headers=H())
    status_val = r.json().get("status") if r.status_code == 200 else None
    tc = r.json().get("table_code") if r.status_code == 200 else None
    log(15, f"GET import job → status={status_val}, table_code={tc}", r.status_code == 200 and status_val == "READY", r.status_code, r.text[:200])

    r = req.post(f"{BASE}/api/v2/import/jobs/{job_id}/commit", headers=H())
    log(16, "POST /api/v2/import/jobs/{id}/commit", r.status_code in (200, 201), r.status_code, r.text[:200])
    time.sleep(2)

    r = req.get(f"{BASE}/api/v2/import/jobs/{job_id}", headers=H())
    final_status = r.json().get("status") if r.status_code == 200 else None
    final_tc = r.json().get("table_code") if r.status_code == 200 else None
    log(17, f"GET job (final) → status={final_status}, table_code={final_tc}", final_status == "COMPLETED", r.status_code, r.text[:200])
else:
    for s in (15, 16, 17):
        log(s, f"Step {s} skipped (no job_id)", False, 0, "no job from step 14")

r = req.get(f"{BASE}/api/forms/daihui_entry/records?page_size=3", headers=H())
ok = r.status_code == 200
data3 = r.json() if ok else {}
total3 = data3.get("total", 0)
log(18, f"GET daihui_entry records → total={total3}", ok and total3 > 0, r.status_code, r.text[:300])

# ══════════════════════════════════════════════════════════
# Phase 7: Cleanup
# ══════════════════════════════════════════════════════════
print("\n╔═ Phase 7: Cleanup ═══════════════════════════════════╗")

if state.get("first_rec_id"):
    r = req.delete(f"{BASE}/api/forms/sim_form/records/{state['first_rec_id']}", headers=H())
    log(19, "DELETE one sim_form record", r.status_code in (200, 204), r.status_code, r.text)
else:
    log(19, "DELETE one record (no id)", False, 0, "no record id")

r = req.delete(f"{BASE}/api/forms/sim_form", headers=H())
log(20, "DELETE /api/forms/sim_form", r.status_code in (200, 204), r.status_code, r.text)

if state.get("op_user_id"):
    r = req.delete(f"{BASE}/api/auth/users/{state['op_user_id']}", headers=H())
    log(21, "DELETE operator user", r.status_code in (200, 204), r.status_code, r.text)
else:
    log(21, "DELETE operator user (no id)", False, 0, "no user id")

# ══════════════════════════════════════════════════════════
# Phase 8: Final Verify
# ══════════════════════════════════════════════════════════
print("\n╔═ Phase 8: Final Verification ════════════════════════╗")

r = req.get(f"{BASE}/api/forms", headers=H())
forms_after = r.json() if r.status_code == 200 else []
codes_after = [f.get("code") for f in forms_after] if isinstance(forms_after, list) else []
log(22, f"GET /api/forms → sim_form absent ({codes_after[:6]})", r.status_code == 200 and "sim_form" not in codes_after, r.status_code)

r = req.get(f"{BASE}/api/auth/users", headers=H())
users_after = r.json() if r.status_code == 200 else []
unames_after = [u.get("username") for u in users_after] if isinstance(users_after, list) else []
log(23, f"GET /api/auth/users → op_sim absent ({unames_after})", r.status_code == 200 and op_name not in unames_after, r.status_code)

r = req.get(f"{BASE}/healthz/detailed")
log(24, "GET /healthz/detailed → system healthy", r.status_code == 200, r.status_code, r.text[:300])

# ══════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════
total_steps = len(results)
passes = sum(1 for t, *_ in results if t == "PASS")
fails = sum(1 for t, *_ in results if t == "FAIL")

print(f"\n{'='*60}")
print("HUMAN SIMULATION TEST SUMMARY")
print(f"{'='*60}")
print(f"Total: {total_steps}  |  PASS: {passes}  |  FAIL: {fails}")
print()

for tag, step, label, code, body in results:
    icon = "✓" if tag == "PASS" else "✗"
    print(f"  [{icon}] {step:2d}. {label}")

if fails:
    print(f"\n{'='*60}")
    print("FAIL DETAILS")
    print(f"{'='*60}")
    for tag, step, label, code, body in results:
        if tag == "FAIL":
            print(f"\nStep {step}: {label}")
            print(f"  HTTP {code}")
            if body:
                print(f"  {body[:600]}")
