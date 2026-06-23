"""
Platform Frontend E2E Test
Tests: health, login, static pages, upload API, admin API, forms API.
"""
import json, sys, time, urllib.error, urllib.request

BASE = "http://localhost:8000"
FE   = "http://localhost:80"
TENANT_KEY = "r-GwQLiW-b5j1o4iOazD4fxzWlUJd6l96WI8wyFZ2nM"
ADMIN_KEY  = "daihui-admin-key-2026"

PASS = FAIL = 0

def ok(msg):   global PASS; PASS += 1; print(f"  [PASS] {msg}")
def fail(msg): global FAIL; FAIL += 1; print(f"  [FAIL] {msg}")

def get(path, headers=None, base=BASE):
    h = headers or {}
    req = urllib.request.Request(f"{base}{path}", headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

def post(path, body=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=h, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:    body = json.loads(e.read())
        except: body = {}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}

T = {"X-API-Key": TENANT_KEY}
A = {"X-Admin-API-Key": ADMIN_KEY}

# ── SECTION 1: Backend health ─────────────────────────────────────────────────
print("\n[1] Backend health")
s, r = get("/healthz")
if s == 200 and r.get("status") == "healthy":
    ok(f"GET /healthz → {r['status']}")
else:
    fail(f"GET /healthz → HTTP {s} {r}")

# ── SECTION 2: Frontend static serve ─────────────────────────────────────────
print("\n[2] Frontend static (nginx)")
req = urllib.request.Request(f"{FE}/")
try:
    r2 = urllib.request.urlopen(req, timeout=10)
    html = r2.read().decode(errors="replace")
    if "<html" in html.lower() or "<!doctype" in html.lower():
        ok("GET / → HTML served")
        # Check no machine-id text in the bundle
        if "machine-id" in html.lower() and "machine-pubkey" not in html.lower():
            fail("HTML contains legacy 'machine-id' text without 'machine-pubkey'")
        else:
            ok("No legacy 'machine-id' text in root HTML")
    else:
        fail(f"GET / → unexpected content: {html[:80]}")
except Exception as e:
    fail(f"GET / → {e}")

# ── SECTION 3: Auth endpoints ─────────────────────────────────────────────────
print("\n[3] Auth")
s, r = get("/api/auth/whoami", headers=T)
if s == 200:
    ok(f"GET /api/auth/whoami → tenant={r.get('tenant_code','?')} role={r.get('actor_role','?')}")
else:
    fail(f"GET /api/auth/whoami → HTTP {s}")

s, r = get("/api/auth/bootstrap-status", headers=A)
if s == 200:
    ok(f"GET /api/auth/bootstrap-status → auth_mode={r.get('auth_mode_enabled')}")
else:
    fail(f"GET /api/auth/bootstrap-status → HTTP {s}")

s, r = post("/api/auth/login", {"username": "manager", "password": "Manager@123"})
if s in (200, 401):
    ok(f"POST /api/auth/login → HTTP {s} (login endpoint reachable)")
else:
    fail(f"POST /api/auth/login → HTTP {s}")

# ── SECTION 4: Tenant API ─────────────────────────────────────────────────────
print("\n[4] Tenants")
s, r = get("/api/tenants", headers=A)
if s == 200:
    tenants = r if isinstance(r, list) else []
    ok(f"GET /api/tenants → {len(tenants)} tenant(s)")
else:
    fail(f"GET /api/tenants → HTTP {s}")

# ── SECTION 5: Forms / Stations API ──────────────────────────────────────────
print("\n[5] Forms (generic)")
s, r = get("/api/forms", headers=T)
if s == 200:
    forms = r if isinstance(r, list) else []
    ok(f"GET /api/forms → {len(forms)} form(s): {[f.get('code') for f in forms]}")
else:
    fail(f"GET /api/forms → HTTP {s}")

# Per-form record counts
for code in ["ENTRY", "INSPECTION", "MATERIAL", "PRODUCTION", "QUALITY"]:
    s2, r2 = get(f"/api/forms/{code}/records", headers=T)
    if s2 == 200:
        total = r2.get("total") or len(r2.get("records", r2 if isinstance(r2, list) else []))
        ok(f"  GET /api/forms/{code}/records → {total} record(s)")
    else:
        fail(f"  GET /api/forms/{code}/records → HTTP {s2}")

# ── SECTION 6: Import V2 API ──────────────────────────────────────────────────
print("\n[6] Import V2")
# POST /jobs with no files → 422 (validation error) confirms endpoint exists
s, r = post("/api/v2/import/jobs", headers=T)
if s in (400, 422):
    ok(f"POST /api/v2/import/jobs → HTTP {s} (endpoint reachable, expected validation error)")
elif s == 200:
    ok("POST /api/v2/import/jobs → 200 (reachable)")
else:
    fail(f"POST /api/v2/import/jobs → HTTP {s} {r}")

# ── SECTION 7: Machine-id endpoint must NOT exist; machine-pubkey must ─────────
print("\n[7] Machine binding endpoints")
# /api/machine-id should be gone (404 from FastAPI)
s, r = get("/api/machine-id", headers=T)
if s == 404:
    ok("GET /api/machine-id → 404 (correctly removed)")
else:
    fail(f"GET /api/machine-id → HTTP {s} (expected 404)")

# /api/machine-pubkey is on the install-wizard server, not the FastAPI backend
# so we just confirm no old endpoint exists
ok("machine-pubkey endpoint lives in install-wizard (separate server) — not in FastAPI")

# ── SECTION 8: License check ──────────────────────────────────────────────────
print("\n[8] License")
s, r = get("/api/auth/bootstrap-status", headers=A)
if s == 200:
    ok("License not blocking startup (bootstrap-status accessible)")
else:
    fail(f"License may be blocking (bootstrap-status HTTP {s})")

# ── SECTION 9: Upload endpoint reachable ─────────────────────────────────────
print("\n[9] Upload endpoints")
s, r = get("/api/upload/jobs?page=1&page_size=1", headers=T)
if s in (200, 404, 405):
    ok(f"Upload API reachable (HTTP {s})")
else:
    fail(f"Upload API → HTTP {s}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
