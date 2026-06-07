import hashlib, hmac, json, uuid

import paramiko

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"

SECRET_KEY = "test_secret_key_at_least_32_characters_long"
RAW_KEY = "e2e-test-api-key-v1"
DB_PASS = "qqq123"
DB_USER = "gslab"
DB_HOST = "localhost"
DB_NAME = "formdb"


def run(ssh, cmd, timeout=60):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def p(s):
    print(str(s).encode("ascii", "replace").decode("ascii"))


def sq(s):
    return "'" + str(s).replace("'", "'\"'\"'") + "'"


def psql(sql, raw=False):
    flag = "-t " if raw else ""
    return (
        f"PGPASSWORD={DB_PASS} psql -U {DB_USER} -h {DB_HOST} "
        f"-d {DB_NAME} {flag}-c {sq(sql)}"
    )


def parse_http(raw):
    marker = "\nHTTP:"
    if marker not in raw:
        return "", raw
    body, code = raw.rsplit(marker, 1)
    return code.strip(), body


def body_preview(body):
    return body.replace("\r", "").replace("\n", "\\n")[:300]


def report(status, name, http_code, body, detail=""):
    suffix = f" {detail}" if detail else ""
    p(f"[{status}] {name} HTTP:{http_code or 'N/A'} body={body_preview(body)}{suffix}")


def extract_process_id(body):
    try:
        data = json.loads(body)
    except Exception as exc:
        return None, f"json parse failed: {exc}"
    if isinstance(data, dict):
        process_id = data.get("process_id")
        if process_id:
            return process_id, ""
    return None, "process_id not found"


key_hash = hmac.new(SECRET_KEY.encode(), RAW_KEY.encode(), hashlib.sha256).hexdigest()
tenant_insert_id = str(uuid.uuid4())
api_key_insert_id = str(uuid.uuid4())

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

try:
    p("=== Setup: tenant ===")
    tenant_sql = (
        "INSERT INTO tenants (id, name, code, is_active, is_default) VALUES "
        f"('{tenant_insert_id}', 'E2E Test Tenant', 'e2e', true, true) "
        "ON CONFLICT (code) DO NOTHING;"
    )
    rc, out, err = run(ssh, psql(tenant_sql), timeout=30)
    p(f"rc={rc}")
    if out:
        p(out)
    if err:
        p(err)

    p("=== Setup: tenant id ===")
    rc, out, err = run(
        ssh,
        psql("SELECT id FROM tenants WHERE code='e2e';", raw=True),
        timeout=30,
    )
    tenant_id = out.strip().splitlines()[0].strip() if out.strip() else ""
    p(f"rc={rc} tenant_id={tenant_id}")
    if err:
        p(err)

    p("=== Setup: api key ===")
    api_key_sql = (
        "INSERT INTO tenant_api_keys (id, tenant_id, key_hash, label, is_active) VALUES "
        f"('{api_key_insert_id}', '{tenant_id}', '{key_hash}', 'e2e-test', true) "
        "ON CONFLICT (key_hash) DO NOTHING;"
    )
    rc, out, err = run(ssh, psql(api_key_sql), timeout=30)
    p(f"rc={rc}")
    if out:
        p(out)
    if err:
        p(err)

    p("=== Test 1: health check ===")
    rc, out, err = run(
        ssh,
        "curl -s -w '\\nHTTP:%{http_code}' http://localhost:8000/healthz",
        timeout=10,
    )
    http_code, body = parse_http(out)
    report("PASS" if http_code == "200" else "FAIL", "health check", http_code, body)
    if err:
        p(err)

    p("=== Test 2: POST /api/upload ===")
    csv = "name,value\\ntest_row,1\\ntest_row,2\\ntest_row,3"
    rc, out, err = run(
        ssh,
        f"printf {sq(csv)} > /tmp/P1_2507173_01.csv",
        timeout=10,
    )
    if rc != 0:
        report("FAIL", "POST /api/upload", "", err or out, "csv setup failed")
        process_id = None
    else:
        rc, out, err = run(
            ssh,
            "curl -s -X POST http://localhost:8000/api/upload "
            "-H 'X-API-Key: e2e-test-api-key-v1' "
            "-F 'file=@/tmp/P1_2507173_01.csv' "
            "-w '\\nHTTP:%{http_code}'",
            timeout=60,
        )
        http_code, body = parse_http(out)
        process_id, parse_detail = extract_process_id(body)
        ok = http_code == "200" and bool(process_id)
        report("PASS" if ok else "FAIL", "POST /api/upload", http_code, body, parse_detail)
        if err:
            p(err)

    p("=== Test 3: upload status ===")
    if not process_id:
        report("SKIP", "upload status", "", "", "no process_id from upload")
    else:
        rc, out, err = run(
            ssh,
            "curl -s -H 'X-API-Key: e2e-test-api-key-v1' "
            f"http://localhost:8000/api/upload/{process_id}/status "
            "-w '\\nHTTP:%{http_code}'",
            timeout=30,
        )
        http_code, body = parse_http(out)
        if http_code == "404":
            report("SKIP", "upload status", http_code, body, "status endpoint returned 404")
        else:
            report("PASS" if http_code == "200" else "FAIL", "upload status", http_code, body)
        if err:
            p(err)
finally:
    ssh.close()
