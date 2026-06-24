"""
test_config_envfile.py — 驗證 config.py 從 system/.env 載入設定，
即使 cwd 是 system/backend/（重現安裝精靈 bootstrap 情境）。
需 pydantic + pydantic-settings。在 Docker python:3.11 內執行。
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

PASS = FAIL = 0
def ok(m):   global PASS; PASS += 1; print(f"  [PASS] {m}")
def fail(m): global FAIL; FAIL += 1; print(f"  [FAIL] {m}")

print("=" * 60)
print("  config.py .env Resolution Test")
print("=" * 60)

# 來源 config.py（已修正的 dist 版本）
SRC_CONFIG = Path("/src/dist/client-deploy-gui-selected-form-system/system/backend/app/core/config.py")

work = Path(tempfile.mkdtemp(prefix="cfgtest_"))
# 建立 system/backend/app/core/ 結構
core_dir = work / "system" / "backend" / "app" / "core"
core_dir.mkdir(parents=True)
(work / "system" / "backend" / "app" / "__init__.py").write_text("")
(work / "system" / "backend" / "app" / "core" / "__init__.py").write_text("")
shutil.copy(SRC_CONFIG, core_dir / "config.py")

# .env 寫在 system/.env（安裝精靈的位置），SECRET_KEY 為合法強金鑰
system_dir = work / "system"
(system_dir / ".env").write_text(
    "DATABASE_URL='sqlite+aiosqlite:///test.db'\n"
    "SECRET_KEY='a-strong-rotated-secret-key-32chars-minimum-xyz'\n"
    "ENVIRONMENT='production'\n"
    "ADMIN_API_KEYS='test-admin-key'\n",
    encoding="utf-8",
)
ok("建立 system/.env（含合法 SECRET_KEY, ENVIRONMENT=production）")

# 切到 system/backend/（重現 bootstrap 的 cwd），這裡沒有 .env
backend_dir = system_dir / "backend"
os.chdir(backend_dir)
ok(f"chdir 到 {backend_dir.name}/（此處無 .env，重現原始 bug 情境）")

# 確認 backend/.env 不存在（純測 config.py 絕對路徑解析）
if not (backend_dir / ".env").exists():
    ok("backend/.env 不存在 — 僅靠 config.py 絕對路徑解析")

# import config 並建立 Settings
sys.path.insert(0, str(backend_dir))
try:
    from app.core import config as cfg
    env_files = cfg._resolve_env_files()
    print(f"  INFO  解析的 .env 候選：{[Path(p).parent.name + '/.env' for p in env_files]}")
    settings = cfg.get_settings()
    ok("Settings() 建立成功（無 ValidationError）")
    if settings.secret_key == "a-strong-rotated-secret-key-32chars-minimum-xyz":
        ok("SECRET_KEY 從 system/.env 正確載入")
    else:
        fail(f"SECRET_KEY 不符：{settings.secret_key[:20]}...")
    if str(settings.database_url).startswith("sqlite"):
        ok("DATABASE_URL 從 system/.env 正確載入")
    else:
        fail(f"DATABASE_URL 不符：{settings.database_url}")
except Exception as e:
    fail(f"Settings() 失敗：{type(e).__name__}: {str(e)[:120]}")

os.chdir("/")
shutil.rmtree(work, ignore_errors=True)

print(f"\n{'='*60}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
