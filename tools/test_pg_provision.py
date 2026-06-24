"""
test_pg_provision.py — 驗證 install-wizard 的 PostgreSQL 自動佈建。
在 Docker (ubuntu + postgresql) 內以 root 執行。
重現用戶情境：全新機器、PostgreSQL 無 form_system role/db。
"""
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

PASS = FAIL = 0
def ok(m):   global PASS; PASS += 1; print(f"  [PASS] {m}")
def fail(m): global FAIL; FAIL += 1; print(f"  [FAIL] {m}")

print("=" * 60)
print("  PostgreSQL Provisioning Test")
print("=" * 60)

# 動態載入 install-wizard.py（避免 import 名稱含 '-' 的問題）
WIZ = Path("/src/tools/install-wizard.py")
spec = importlib.util.spec_from_file_location("install_wizard", WIZ)
wiz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wiz)
ok("載入 install-wizard.py 模組")

DB_NAME = "form_system"
DB_USER = "form_system"
DB_PASS = "test-pg-pass-2026"

env = {
    "DATABASE_URL": f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@localhost:5432/{DB_NAME}",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": DB_NAME,
    "DB_USERNAME": DB_USER,
    "DB_PASSWORD": DB_PASS,
}

# 佈建前：確認 role/db 不存在
print("\n[1] 佈建前狀態")
if not wiz._pg_db_exists(DB_NAME):
    ok(f"database '{DB_NAME}' 佈建前不存在（重現全新機器情境）")
else:
    print(f"  INFO  database '{DB_NAME}' 已存在（將測試 idempotent）")

# 執行佈建
print("\n[2] 執行 _provision_postgres_linux")
result = wiz._provision_postgres_linux(env, print)
if result:
    ok("佈建回傳 True（成功）")
else:
    fail("佈建回傳 False（需手動處理）")

# 佈建後：role + db 存在
print("\n[3] 佈建後驗證")
if wiz._pg_db_exists(DB_NAME):
    ok(f"database '{DB_NAME}' 已建立")
else:
    fail(f"database '{DB_NAME}' 仍不存在")

# 實際用 asyncpg 連線（用戶的失敗點）
print("\n[4] asyncpg 連線測試（用戶原始失敗點）")
async def _test_conn():
    import asyncpg
    conn = await asyncpg.connect(
        host="localhost", port=5432,
        user=DB_USER, password=DB_PASS, database=DB_NAME,
    )
    val = await conn.fetchval("SELECT 1")
    await conn.close()
    return val

try:
    v = asyncio.run(_test_conn())
    if v == 1:
        ok("asyncpg 連線成功（password authentication 通過）")
    else:
        fail(f"asyncpg 連線回傳異常：{v}")
except Exception as e:
    fail(f"asyncpg 連線失敗：{type(e).__name__}: {str(e)[:100]}")

# 二次佈建（idempotent）
print("\n[5] 二次佈建（idempotent）")
result2 = wiz._provision_postgres_linux(env, print)
if result2:
    ok("二次佈建仍回傳 True（idempotent）")
else:
    fail("二次佈建失敗")

print(f"\n{'='*60}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
