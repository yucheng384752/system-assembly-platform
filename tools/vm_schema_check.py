"""Check station_schemas table structure and run fixed migration."""
import paramiko, stat, time, sys

HOST = "192.168.200.33"
USER = "gslab"
PASS = "qqq123"
DEPLOY_DIR = "/home/gslab/Desktop/form-system-import-query-analytics-generic-forms-deploy-2026-06-26"
BACKEND_DIR = f"{DEPLOY_DIR}/system/backend"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

def psql(sql, desc=""):
    cmd = f"PGPASSWORD=qqq123 psql -h localhost -U form_system -d form_system -c \"{sql}\" 2>&1"
    print(f"\n[{desc}]"); print("-"*60)
    _, stdout, _ = client.exec_command(cmd, timeout=20)
    out = stdout.read().decode(errors="replace").strip()
    print(out)
    return out

# 查 station_schemas 欄位
psql("\\d station_schemas", "station_schemas columns")
psql("SELECT COUNT(*) FROM station_schemas", "station_schemas count")
psql("SELECT id, station_id, is_active FROM station_schemas LIMIT 5", "station_schemas sample")

# 查 generic_records 欄位
psql("\\d generic_records", "generic_records columns")

client.close()
