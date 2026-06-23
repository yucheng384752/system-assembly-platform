"""E2E test: upload all 5 Daihui CSVs, validate, commit, verify generic_records."""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "http://localhost:8000"
TENANT_KEY = "r-GwQLiW-b5j1o4iOazD4fxzWlUJd6l96WI8wyFZ2nM"
CSV_DIR = Path(r"C:\Users\gslab\Desktop\岱暉資料表\處理完畢")

FILE_TO_CODE = {
    "entry_horizontal.csv": "ENTRY",
    "inspection_horizontal.csv": "INSPECTION",
    "material_horizontal.csv": "MATERIAL",
    "production_horizontal.csv": "PRODUCTION",
    "quality_horizontal.csv": "QUALITY",
}


def request(method, path, data=None, headers=None, content_type=None):
    h = {"X-API-Key": TENANT_KEY}
    if headers:
        h.update(headers)
    if content_type:
        h["Content-Type"] = content_type
    req = urllib.request.Request(f"{API}{path}", data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body.decode(errors="replace")}


def upload_csv(filename, table_code):
    filepath = CSV_DIR / filename
    file_bytes = filepath.read_bytes()
    boundary = uuid.uuid4().hex.encode()
    crlf = b"\r\n"
    body = (
        b"--" + boundary + crlf
        + b'Content-Disposition: form-data; name="table_code"' + crlf + crlf
        + table_code.encode() + crlf
        + b"--" + boundary + crlf
        + b'Content-Disposition: form-data; name="allow_duplicate"' + crlf + crlf
        + b"true" + crlf
        + b"--" + boundary + crlf
        + b'Content-Disposition: form-data; name="files"; filename="' + filename.encode() + b'"' + crlf
        + b"Content-Type: text/csv" + crlf + crlf
        + file_bytes + crlf
        + b"--" + boundary + b"--" + crlf
    )
    ct = f"multipart/form-data; boundary={boundary.decode()}"
    status, resp = request("POST", "/api/v2/import/jobs", data=body, content_type=ct)
    return status, resp


def wait_for_status(job_id, target_statuses, max_wait=30):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        status, resp = request("GET", f"/api/v2/import/jobs/{job_id}")
        if resp.get("status") in target_statuses:
            return resp
        time.sleep(1)
    return resp


def validate_job(job_id):
    status, resp = request("POST", f"/api/v2/import/jobs/{job_id}/validate",
                           data=b"{}", content_type="application/json")
    return status, resp


def commit_job(job_id):
    status, resp = request("POST", f"/api/v2/import/jobs/{job_id}/commit",
                           data=b"{}", content_type="application/json")
    return status, resp


PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


print("=" * 60)
print("  Daihui CSV Upload E2E Test")
print("=" * 60)

job_ids = {}

# --- PHASE 1: Upload ---
print("\n[Phase 1] Upload CSVs")
for filename, table_code in FILE_TO_CODE.items():
    if not (CSV_DIR / filename).exists():
        fail(f"CSV not found: {filename}")
        continue
    status, resp = upload_csv(filename, table_code)
    if status in (200, 201) and resp.get("id"):
        job_id = resp["id"]
        job_ids[filename] = job_id
        ok(f"{filename} → {table_code} → job {job_id[:8]}… (status={resp.get('status')})")
    else:
        fail(f"{filename} upload failed: HTTP {status} {resp}")

if not job_ids:
    print("\n[ABORT] No jobs created.")
    sys.exit(1)

# --- PHASE 2: Wait for auto-validation (background task) ---
print("\n[Phase 2] Wait for auto-validation (background)")
ready_jobs = {}
for filename, job_id in job_ids.items():
    job_state = wait_for_status(job_id, ("READY", "FAILED", "COMPLETED"), max_wait=30)
    js = job_state.get("status")
    ec = job_state.get("error_count", "?")
    if js == "READY":
        ready_jobs[filename] = job_id
        ok(f"{filename} → READY (error_count={ec})")
    else:
        fail(f"{filename} → {js} (expected READY, error_count={ec})")

# --- PHASE 3: Commit ---
print("\n[Phase 3] Commit jobs")
committed = []
for filename, job_id in ready_jobs.items():
    status, resp = commit_job(job_id)
    if status in (200, 202):
        job_state = wait_for_status(job_id, ("COMPLETED", "FAILED"), max_wait=20)
        if job_state.get("status") == "COMPLETED":
            committed.append(filename)
            ok(f"{filename} → COMPLETED (committed_count={job_state.get('committed_count', '?')})")
        else:
            fail(f"{filename} → {job_state.get('status')} after commit, error_summary={job_state.get('error_summary')}")
    else:
        fail(f"{filename} commit HTTP {status}: {resp}")

# --- PHASE 4: DB verification via /api/forms/{code}/records ---
print("\n[Phase 4] Verify generic_records via API")
code_for_file = {v: k for k, v in FILE_TO_CODE.items()}
for table_code in FILE_TO_CODE.values():
    status, resp = request("GET", f"/api/forms/{table_code}/records")
    if status == 200:
        count = resp.get("total") or len(resp.get("records", resp if isinstance(resp, list) else []))
        if count and int(count) > 0:
            ok(f"{table_code}: {count} record(s) in generic_records")
        else:
            fail(f"{table_code}: 0 records in generic_records (response={resp})")
    else:
        fail(f"{table_code}: GET /api/forms/{table_code}/records → HTTP {status}")

print(f"\n{'='*60}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
