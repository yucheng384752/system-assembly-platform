import paramiko, time

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"

def run(ssh, cmd, timeout=120):
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err

def sudo(ssh, cmd, timeout=120):
    return run(ssh, f"echo '{PASS}' | sudo -S {cmd}", timeout=timeout)

def p(s):
    print(s.encode("ascii", "replace").decode("ascii"))

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=15)

p("=== Installing PostgreSQL ===")
rc, out, err = sudo(ssh, "apt-get install -y postgresql postgresql-client 2>&1", timeout=300)
p(f"rc={rc}")
p((out + err)[-1000:])

p("=== Starting PostgreSQL ===")
rc, out, err = sudo(ssh, "systemctl start postgresql", timeout=30)
p(f"rc={rc}: " + err)

time.sleep(2)

p("=== Check port 5432 ===")
rc, out, err = run(ssh, "ss -tlnp | grep 5432")
p(out or "(not listening)")

p("=== Setup database user and DB ===")
# Create user gslab with password and create formdb
setup_sql = """
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gslab') THEN
    CREATE ROLE gslab WITH LOGIN PASSWORD 'qqq123' CREATEDB;
  END IF;
END \$\$;
"""
rc, out, err = sudo(ssh, f"""su - postgres -c "psql -c \\"DO \\\\\\$\\\\\\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gslab') THEN CREATE ROLE gslab WITH LOGIN PASSWORD 'qqq123' CREATEDB; END IF; END \\\\\\$\\\\\\$;\\"" """, timeout=30)
p(f"create role rc={rc}: " + out + err)

rc, out, err = sudo(ssh, """su - postgres -c "createdb -O gslab formdb 2>&1 || echo 'DB may exist'" """, timeout=30)
p(f"createdb rc={rc}: " + out + err)

p("=== Test connection ===")
rc, out, err = run(ssh, "psql -U gslab -h localhost -d formdb -c 'SELECT 1' 2>&1")
p(f"rc={rc}: " + out + err)

ssh.close()
