import json
import sys

import paramiko

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
DEST = "/home/gslab/deploy-test-v12/system"
VENV_PYTHON = f"{DEST}/venv/bin/python3"


def run(ssh, cmd, timeout=60):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def p(s):
    print(s.encode("ascii", "replace").decode("ascii"))


def parse_bootstrap_json(out):
    text = out.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    ssh.connect(HOST, username=USER, password=PASS, timeout=15)

    rc, out, err = run(ssh, f"test -x {VENV_PYTHON} && echo {VENV_PYTHON} || echo python3")
    python_cmd = out.strip() or "python3"
    p(f"=== Python ===\n{python_cmd}")

    bootstrap_cmd = (
        f"cd {DEST}/backend && "
        f"export $(grep -v '^\\#' {DEST}/.env | xargs) && "
        f"{python_cmd} -m app.core.generated_db_bootstrap 2>&1"
    )

    p("=== Bootstrap ===")
    rc, out, err = run(ssh, bootstrap_cmd, timeout=60)
    p(out)
    if rc != 0:
        if err:
            p("=== Bootstrap stderr ===")
            p(err)
        sys.exit(f"bootstrap failed with rc={rc}")

    try:
        data = parse_bootstrap_json(out)
    except json.JSONDecodeError as exc:
        sys.exit(f"failed to parse bootstrap JSON: {exc}")

    tables = data.get("tables")
    table_count = data.get("tableCount")
    p("=== Bootstrap tables ===")
    p(json.dumps(tables, indent=2))
    p(f"tableCount={table_count}")

    p("=== psql \\dt ===")
    rc, out, err = run(
        ssh,
        "PGPASSWORD=qqq123 psql -U gslab -h localhost -d formdb -c '\\dt' 2>&1",
        timeout=60,
    )
    p(out)
    if err:
        p("=== psql stderr ===")
        p(err)
    if rc != 0:
        sys.exit(f"psql \\dt failed with rc={rc}")
finally:
    ssh.close()
