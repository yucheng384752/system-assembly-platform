import paramiko

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"

def run(ssh, cmd, timeout=30):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err

def p(s):
    print(s.encode("ascii", "replace").decode("ascii"))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

p("=== PostgreSQL status ===")
rc, out, err = run(ssh, "systemctl status postgresql --no-pager 2>&1 | head -10")
p(out)

p("=== PostgreSQL version ===")
rc, out, err = run(ssh, "psql --version 2>&1")
p(out)

p("=== Check port 5432 ===")
rc, out, err = run(ssh, "ss -tlnp | grep 5432")
p(out or "(not listening)")

p("=== Try starting PostgreSQL ===")
rc, out, err = run(ssh, "sudo systemctl start postgresql 2>&1")
p(f"rc={rc}: " + out + err)

p("=== After start: port 5432 ===")
rc, out, err = run(ssh, "ss -tlnp | grep 5432")
p(out or "(not listening)")

p("=== Check if formdb exists ===")
rc, out, err = run(ssh, "psql -U postgres -lqt 2>&1 | grep formdb")
p(out or "(formdb not found)")

p("=== psql as gslab ===")
rc, out, err = run(ssh, "psql -U gslab -c '\\l' formdb 2>&1 | head -5")
p(out + err)

ssh.close()
