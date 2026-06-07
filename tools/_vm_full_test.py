"""
完整安裝→執行測試腳本
Phase 1: 清除舊部署，從 ZIP 全新解壓
Phase 2: 寫入 .env，執行 deploy.sh --background
Phase 3: DB Migration (generated_db_bootstrap.py)
Phase 4: E2E API 測試 (health / upload / status)
"""
import hashlib, hmac, json, time, uuid
import paramiko

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
DEPLOY_DIR = "deploy-test-v12"
ZIP = "/home/gslab/client-deploy-mvp-import-flow-v12.zip"
DEST = f"/home/gslab/{DEPLOY_DIR}"
SYSTEM = f"{DEST}/system"
BACKEND = f"{SYSTEM}/backend"

SECRET_KEY = "test_secret_key_at_least_32_characters_long"
RAW_KEY = "e2e-test-api-key-v1"
DB_PASS = "qqq123"
DB_USER = "gslab"
DB_NAME = "formdb"

PASS_COUNT = 0
FAIL_COUNT = 0


def run(ssh, cmd, timeout=120):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def p(s):
    print(str(s).encode("ascii", "replace").decode("ascii"))


def section(title):
    p(f"\n{'='*60}")
    p(f"  {title}")
    p(f"{'='*60}")


def check(name, passed, detail=""):
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    suffix = f" | {detail}" if detail else ""
    p(f"  [{status}] {name}{suffix}")
    return passed


def psql_cmd(sql):
    safe = sql.replace("'", "'\"'\"'")
    return f"PGPASSWORD={DB_PASS} psql -U {DB_USER} -h localhost -d {DB_NAME} -t -c '{safe}'"


def parse_http(raw):
    marker = "\nHTTP:"
    if marker not in raw:
        return "", raw
    body, code = raw.rsplit(marker, 1)
    return code.strip(), body.strip()


def body_preview(body, limit=160):
    return str(body).replace("\r", "").replace("\n", "\\n")[:limit]


def json_field(body, name, default=None):
    try:
        data = json.loads(body)
    except Exception:
        return default
    if isinstance(data, dict):
        return data.get(name, default)
    return default


def wait_for_import_status(ssh, job_id, wanted, timeout_s=45):
    last_status = ""
    last_body = ""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rc, out, err = run(
            ssh,
            f"curl -s -H 'X-API-Key: {RAW_KEY}' "
            f"http://localhost:8000/api/v2/import/jobs/{job_id} "
            f"-w '\\nHTTP:%{{http_code}}'",
            timeout=10,
        )
        http_code, body = parse_http(out)
        last_body = body
        if http_code == "200":
            last_status = str(json_field(body, "status", ""))
            if last_status in wanted:
                return True, last_status, body
            if last_status == "FAILED":
                return False, last_status, body
        time.sleep(2)
    return False, last_status, last_body


def run_deploy_script(ssh, timeout_s=600):
    log_path = "/tmp/deploy-v12.log"
    rc_path = "/tmp/deploy-v12.rc"
    run(ssh, f"rm -f {log_path} {rc_path}", timeout=10)
    start_cmd = (
        "setsid bash -c "
        f"'cd {DEST} && bash deploy.sh --background > {log_path} 2>&1; "
        f"echo $? > {rc_path}' </dev/null >/dev/null 2>&1 & echo started"
    )
    rc, out, err = run(ssh, start_cmd, timeout=10)
    if rc != 0:
        return rc, out, err

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rc, out, err = run(ssh, f"test -f {rc_path} && cat {rc_path} || true", timeout=10)
        if out.strip():
            deploy_rc = int(out.strip().splitlines()[-1])
            _, deploy_out, _ = run(ssh, f"cat {log_path} 2>/dev/null || true", timeout=20)
            return deploy_rc, deploy_out, ""
        time.sleep(5)

    _, deploy_out, _ = run(ssh, f"tail -80 {log_path} 2>/dev/null || true", timeout=20)
    return 124, deploy_out, f"deploy.sh timed out after {timeout_s}s"


# ── Connect ──────────────────────────────────────────────────────────────────
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)
p(f"Connected to {HOST}")

try:
    # ── Phase 1: Clean Install ────────────────────────────────────────────────
    section("Phase 1: Clean Install")

    p("  Killing old uvicorn...")
    run(ssh, "pkill -f 'uvicorn app.main' 2>/dev/null || true")
    run(ssh, f"pkill -f '{DEST}.*deploy.sh|npm install' 2>/dev/null || true")
    time.sleep(1)

    p(f"  Removing {DEST} ...")
    rc, out, err = run(
        ssh,
        "python3 - <<'PY'\n"
        "import shutil\n"
        f"shutil.rmtree('{DEST}', ignore_errors=True)\n"
        "PY\n"
        f"rm -rf {DEST}",
    )
    check("rm old deploy dir", rc == 0, err.strip() or "ok")

    p(f"  Extracting ZIP: {ZIP} -> {DEST}")
    rc, out, err = run(ssh, f"python3 /home/gslab/extract_zip.py {DEST} {ZIP}", timeout=60)
    check("extract ZIP", rc == 0, (out + err).strip()[:120])

    rc, out, err = run(ssh, f"ls {DEST}/")
    check("deploy dir exists", rc == 0 and bool(out.strip()), out.strip()[:80])

    # ── Phase 2: Configure & Start ────────────────────────────────────────────
    section("Phase 2: Configure & Start Backend")

    env_content = "\n".join([
        "DATABASE_URL=postgresql+asyncpg://gslab:qqq123@localhost:5432/formdb",
        "SECRET_KEY=test_secret_key_at_least_32_characters_long",
        "AUTH_MODE=api_key",
        "ENVIRONMENT=development",
        "LOG_LEVEL=INFO",
        "CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:4173",
        "VALID_MATERIALS_CSV=PE,PP,PET,OPP,CPP,NY",
        "VALID_SLITTING_MACHINES_CSV=1,2,3,4,5,6,7,8,9,10",
        "",
    ])
    write_env_cmd = f"mkdir -p {SYSTEM}/logs && cat > {SYSTEM}/.env << 'ENVEOF'\n{env_content}ENVEOF"
    rc, out, err = run(ssh, write_env_cmd)
    check("write .env", rc == 0, err.strip() or "ok")

    p("  Running deploy.sh --background (up to 600s)...")
    rc, out, err = run_deploy_script(ssh, timeout_s=600)
    check("deploy.sh rc=0", rc == 0, f"rc={rc}")
    if out:
        p("  deploy.sh tail:\n" + "\n".join(("    " + l) for l in out.strip().splitlines()[-10:]))

    p("  Waiting 12s for uvicorn to settle...")
    time.sleep(12)

    rc, out, err = run(ssh, f"tail -30 {SYSTEM}/logs/backend.log 2>/dev/null || echo 'NO LOG'")
    startup_ok = "Application startup complete" in out
    check("startup complete in log", startup_ok, "(check backend.log)")
    if not startup_ok:
        p("  --- backend.log tail ---")
        p(out[-1500:])

    rc, out, err = run(ssh, "curl -s -w '\\nHTTP:%{http_code}' http://localhost:8000/healthz", timeout=10)
    http_code, body = parse_http(out)
    check("GET /healthz HTTP 200", http_code == "200", body[:120])

    # ── Phase 3: Verify DB Tables (migration run by deploy.sh) ───────────────
    section("Phase 3: Verify DB Tables")

    rc, out, err = run(ssh, f"PGPASSWORD={DB_PASS} psql -U {DB_USER} -h localhost -d {DB_NAME} -c '\\dt' 2>&1")
    psql_rows = [l for l in out.splitlines() if "| table |" in l]
    check("tables exist (>=10)", len(psql_rows) >= 10, f"table count={len(psql_rows)}")
    check("tenants table present", any("tenants" in l for l in psql_rows), "")
    check("audit_events table present", any("audit_events" in l for l in psql_rows), "")

    # ── Phase 4: E2E API Tests ────────────────────────────────────────────────
    section("Phase 4: E2E API Tests")

    key_hash = hmac.new(SECRET_KEY.encode(), RAW_KEY.encode(), hashlib.sha256).hexdigest()
    tenant_id_new = str(uuid.uuid4())
    api_key_id_new = str(uuid.uuid4())

    # Insert tenant (idempotent)
    sql_tenant = (
        f"INSERT INTO tenants (id, name, code, is_active, is_default) "
        f"VALUES ('{tenant_id_new}', 'E2E Test Tenant', 'e2e', true, true) "
        f"ON CONFLICT (code) DO NOTHING;"
    )
    rc, _, err = run(ssh, psql_cmd(sql_tenant), timeout=15)
    check("insert tenant", rc == 0, err.strip() or "ok")

    # Fetch actual tenant id
    rc, out, _ = run(ssh, psql_cmd("SELECT id FROM tenants WHERE code='e2e';"), timeout=15)
    tenant_id = out.strip().splitlines()[0].strip() if out.strip() else ""
    check("resolve tenant id", bool(tenant_id), tenant_id[:36])

    # Insert API key (idempotent)
    sql_key = (
        f"INSERT INTO tenant_api_keys (id, tenant_id, key_hash, label, is_active) "
        f"VALUES ('{api_key_id_new}', '{tenant_id}', '{key_hash}', 'e2e-test', true) "
        f"ON CONFLICT (key_hash) DO NOTHING;"
    )
    rc, _, err = run(ssh, psql_cmd(sql_key), timeout=15)
    check("insert api key", rc == 0, err.strip() or "ok")

    # Write test CSV
    csv_content = "name,value\\nrow_a,1\\nrow_b,2\\nrow_c,3"
    rc, out, err = run(ssh, f"printf '{csv_content}' > /tmp/P1_2507173_01.csv")
    check("write test CSV", rc == 0, err.strip() or "ok")

    # POST /api/upload
    rc, out, err = run(
        ssh,
        "curl -s -X POST http://localhost:8000/api/upload "
        "-H 'X-API-Key: e2e-test-api-key-v1' "
        "-F 'file=@/tmp/P1_2507173_01.csv' "
        "-w '\\nHTTP:%{http_code}'",
        timeout=30,
    )
    http_code, body = parse_http(out)
    process_id = None
    try:
        data = json.loads(body)
        process_id = data.get("process_id")
        total_rows = data.get("total_rows", -1)
        valid_rows = data.get("valid_rows", -1)
        upload_ok = http_code == "200" and bool(process_id) and total_rows == 3 and valid_rows == 3
        check("POST /api/upload", upload_ok,
              f"HTTP:{http_code} process_id={str(process_id)[:8]}... rows={total_rows}/{valid_rows}")
    except Exception:
        check("POST /api/upload", False, f"HTTP:{http_code} body={body[:120]}")

    # GET /api/upload/{process_id}/status
    if process_id:
        rc, out, err = run(
            ssh,
            f"curl -s -H 'X-API-Key: e2e-test-api-key-v1' "
            f"http://localhost:8000/api/upload/{process_id}/status "
            f"-w '\\nHTTP:%{{http_code}}'",
            timeout=15,
        )
        http_code, body = parse_http(out)
        try:
            data = json.loads(body)
            status_val = data.get("status", "")
            status_ok = http_code == "200" and status_val in ("VALIDATED", "PENDING", "COMPLETED")
            check("GET /api/upload/{id}/status", status_ok, f"HTTP:{http_code} status={status_val}")
        except Exception:
            check("GET /api/upload/{id}/status", http_code == "200", f"HTTP:{http_code} body={body[:120]}")
    else:
        check("GET /api/upload/{id}/status", False, "skipped: no process_id")

    # -- Phase 5: Import Job create/status/commit -------------------------
    section("Phase 5: Import Job API Tests")

    # Setup: insert table_registry rows required by /api/v2/import/jobs
    for tc, dn in [("P1", "P1 Form Records"), ("P2", "P2 Form Records"), ("P3", "P3 Form Records")]:
        sql_tr = (
            f"INSERT INTO table_registry (id, table_code, display_name) "
            f"VALUES (gen_random_uuid(), '{tc}', '{dn}') "
            f"ON CONFLICT (table_code) DO NOTHING;"
        )
        rc, _, err = run(ssh, psql_cmd(sql_tr), timeout=15)
        check(f"insert table_registry({tc})", rc == 0, err.strip() or "ok")

    import_csv = (
        "lot_no,value\\n"
        "2507173_01,101\\n"
        "2507173_01,102\\n"
        "2507173_01,103\\n"
    )
    unique_name = f"/tmp/P1_2507173_01_{int(time.time())}.csv"
    rc, out, err = run(ssh, f"printf '{import_csv}' > {unique_name}", timeout=10)
    check("write import job CSV", rc == 0, err.strip() or "ok")

    rc, out, err = run(
        ssh,
        "curl -s -X POST http://localhost:8000/api/v2/import/jobs "
        f"-H 'X-API-Key: {RAW_KEY}' "
        "-F 'table_code=P1' "
        "-F 'allow_duplicate=true' "
        f"-F 'files=@{unique_name};filename=P1_2507173_01.csv' "
        "-w '\\nHTTP:%{http_code}'",
        timeout=30,
    )
    http_code, body = parse_http(out)
    import_job_id = json_field(body, "id")
    check(
        "POST /api/v2/import/jobs",
        http_code == "201" and bool(import_job_id),
        f"HTTP:{http_code} job_id={str(import_job_id)[:8]}...",
    )

    if import_job_id:
        ready, status_val, status_body = wait_for_import_status(
            ssh, import_job_id, {"READY"}, timeout_s=45
        )
        check(
            "import job reaches READY",
            ready,
            f"status={status_val} body={body_preview(status_body)}",
        )

        if ready:
            rc, out, err = run(
                ssh,
                f"curl -s -X POST -H 'X-API-Key: {RAW_KEY}' "
                f"http://localhost:8000/api/v2/import/jobs/{import_job_id}/commit "
                f"-w '\\nHTTP:%{{http_code}}'",
                timeout=30,
            )
            http_code, body = parse_http(out)
            commit_status = str(json_field(body, "status", ""))
            check(
                "POST /api/v2/import/jobs/{id}/commit",
                http_code == "200" and commit_status in ("COMMITTING", "COMPLETED"),
                f"HTTP:{http_code} status={commit_status}",
            )

            completed, final_status, final_body = wait_for_import_status(
                ssh, import_job_id, {"COMPLETED"}, timeout_s=45
            )
            check(
                "import job reaches COMPLETED",
                completed,
                f"status={final_status} body={final_body[:120]}",
            )
        else:
            check("POST /api/v2/import/jobs/{id}/commit", False, "skipped: not READY")
            check("import job reaches COMPLETED", False, "skipped: not READY")
    else:
        check("import job reaches READY", False, "skipped: no job id")
        check("POST /api/v2/import/jobs/{id}/commit", False, "skipped: no job id")
        check("import job reaches COMPLETED", False, "skipped: no job id")

    # -- Phase 6: Frontend/static and CORS smoke ---------------------------
    section("Phase 6: Frontend and CORS Smoke")

    rc, out, err = run(ssh, f"test -d {SYSTEM}/frontend/dist && echo yes || echo no")
    check("frontend dist built", out.strip() == "yes", out.strip())

    rc, out, err = run(
        ssh,
        "curl -s -D - -o /dev/null -w '\\nHTTP:%{http_code}' "
        "-X OPTIONS http://localhost:8000/api/v2/import/jobs "
        "-H 'Origin: http://localhost:5173' "
        "-H 'Access-Control-Request-Method: POST' "
        "-H 'Access-Control-Request-Headers: x-api-key'",
        timeout=10,
    )
    http_code, headers = parse_http(out)
    cors_ok = http_code == "200" and "access-control-allow-origin" in headers.lower()
    check("CORS preflight for frontend origin", cors_ok, body_preview(headers, 200))

    # ── Summary ───────────────────────────────────────────────────────────────
    section(f"Summary: {PASS_COUNT} PASS / {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        p("  ALL TESTS PASSED")
    else:
        p(f"  {FAIL_COUNT} test(s) failed — review output above")

finally:
    ssh.close()
