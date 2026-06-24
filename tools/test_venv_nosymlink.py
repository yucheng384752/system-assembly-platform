"""
test_venv_nosymlink.py — 驗證 no-symlink 檔案系統的 venv 建立繞過邏輯。
模擬 VirtualBox 共享資料夾（vboxsf）情境：預建 lib64 真實目錄 + --copies。
在 Docker Linux 內執行。
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PASS = FAIL = 0
def ok(m):   global PASS; PASS += 1; print(f"  [PASS] {m}")
def fail(m): global FAIL; FAIL += 1; print(f"  [FAIL] {m}")

print("=" * 60)
print("  Venv No-Symlink Workaround Test")
print("=" * 60)

work = Path(tempfile.mkdtemp(prefix="venvtest_"))
venv_path = work / ".venv"

# ── 模擬 _create_venv 的 no-symlink 分支 ──────────────────────
print("\n[1] no-symlink 分支：預建 lib64 + --copies")
if venv_path.exists():
    shutil.rmtree(venv_path, ignore_errors=True)
(venv_path / "lib64").mkdir(parents=True, exist_ok=True)
ok("預建 .venv/lib64 真實目錄")

rc = subprocess.call([sys.executable, "-m", "venv", "--copies", str(venv_path)])
if rc == 0:
    ok("venv --copies 建立成功（exit 0）")
else:
    fail(f"venv --copies 失敗（exit {rc}）")
    sys.exit(1)

# ── 驗證 lib64 仍是真實目錄（非 symlink）──────────────────────
print("\n[2] lib64 狀態")
lib64 = venv_path / "lib64"
if lib64.is_dir() and not lib64.is_symlink():
    ok("lib64 是真實目錄（非 symlink）— venv 已跳過 symlink 建立")
else:
    fail(f"lib64 狀態異常（is_symlink={lib64.is_symlink()}）")

# ── 驗證 bin/python 是真實檔案（--copies 應複製非 symlink）─────
print("\n[3] bin/python 狀態")
py = venv_path / "bin" / "python"
if py.exists() and not py.is_symlink():
    ok("bin/python 是複製檔（非 symlink）")
elif py.is_symlink():
    fail("bin/python 仍是 symlink（--copies 未生效）")
else:
    fail("bin/python 不存在")

# ── 驗證 venv 可用：pip 安裝一個小套件 ────────────────────────
print("\n[4] venv 可用性（pip install）")
pip = venv_path / "bin" / "pip"
if pip.exists():
    ok("pip 存在")
    rc = subprocess.call([str(pip), "install", "-q", "--disable-pip-version-check", "six"])
    if rc == 0:
        ok("pip install six 成功（venv 完全可用）")
    else:
        fail(f"pip install 失敗（exit {rc}）")
else:
    fail("pip 不存在")

# ── 驗證 import 能運作 ────────────────────────────────────────
print("\n[5] venv python import")
rc = subprocess.call([str(py), "-c", "import six; print('six', six.__version__)"])
if rc == 0:
    ok("venv python 可 import 已安裝套件")
else:
    fail("venv python import 失敗")

shutil.rmtree(work, ignore_errors=True)

print(f"\n{'='*60}")
print(f"  PASS: {PASS}  FAIL: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
