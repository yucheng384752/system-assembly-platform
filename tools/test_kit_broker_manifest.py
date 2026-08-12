"""
Static verification tests for kit broker activation (thread 20260701-kit-broker-activation).

Tests per the thread's Test Plan:
  1. form-analysis.kit-manifest.json parses as valid JSON
  2. platform-core-kit declares all broker source files
  3. platform-core-kit declares /api/kit routerRegistration
  4. All declared broker source files physically exist
  5. client-deploy dist includes broker files and /api/kit registry
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO / "kits" / "form-analysis.kit-manifest.json"
KIT_SRC = REPO / "kits" / "platform-core-kit" / "src"
DIST_BACKEND = REPO / "dist" / "client-deploy-gui-selected-form-system" / "system" / "backend"

REQUIRED_BROKER_PATHS = [
    "backend/app/api/routes_kit_broker.py",
    "backend/app/core/kit_contracts.py",
    "backend/app/core/kit_broker.py",
    "backend/app/core/db_capabilities.py",
    "frontend/src/services/kitClient.ts",
]

FAILURES: list[str] = []

def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL  {msg}")

def ok(msg: str) -> None:
    print(f"  OK    {msg}")


# ── T1: JSON parse ────────────────────────────────────────────────────────────
print("\n[T1] Manifest JSON parse")
try:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    ok(f"Parsed {MANIFEST_PATH.name}")
except Exception as exc:
    fail(f"Cannot parse manifest: {exc}")
    sys.exit(1)


# ── T2: Broker source paths declared in manifest ─────────────────────────────
print("\n[T2] Broker files declared in manifest")

kits = manifest.get("kits", [])
core_kit = next((k for k in kits if k.get("id") == "platform-core-kit"), {})
declared_sources: set[str] = set()

for section_key in ("routers", "core", "services"):
    for item in core_kit.get("backend", {}).get(section_key, []):
        if isinstance(item, str):
            declared_sources.add(item)
for section_key in ("services", "pages", "components"):
    for item in core_kit.get("frontend", {}).get(section_key, []):
        if isinstance(item, str):
            declared_sources.add(item)

for path in REQUIRED_BROKER_PATHS:
    if path in declared_sources:
        ok(f"Declared: {path}")
    else:
        fail(f"Missing from manifest: {path}")


# ── T3: /api/kit routerRegistration ──────────────────────────────────────────
print("\n[T3] /api/kit routerRegistration")

registrations = (
    core_kit.get("backend", {})
            .get("routerRegistrations", [])
    or []
)
kit_reg = next(
    (r for r in registrations
     if isinstance(r, dict) and r.get("module") == "app.api.routes_kit_broker"),
    None,
)
if kit_reg is None:
    fail("No routerRegistration for app.api.routes_kit_broker")
else:
    ok(f"Found registration: module={kit_reg.get('module')} prefix={kit_reg.get('prefix')}")
    if kit_reg.get("prefix") != "/api/kit":
        fail(f"Wrong prefix: expected /api/kit, got {kit_reg.get('prefix')!r}")
    else:
        ok("prefix=/api/kit")
    if not kit_reg.get("tags"):
        fail("Missing 'tags' in routerRegistration")
    else:
        ok(f"tags={kit_reg.get('tags')}")


# ── T4: Source files physically exist ────────────────────────────────────────
print("\n[T4] Source files exist on disk")

for rel in REQUIRED_BROKER_PATHS:
    full = KIT_SRC / rel
    if full.exists():
        ok(f"Exists: kits/platform-core-kit/src/{rel}")
    else:
        fail(f"Missing on disk: {full}")


# ── T5: Dist client-deploy contains broker files ─────────────────────────────
print("\n[T5] Dist client-deploy-gui contains broker files")

BROKER_DIST_PATHS = [
    "app/api/routes_kit_broker.py",
    "app/core/kit_contracts.py",
    "app/core/kit_broker.py",
    "app/core/db_capabilities.py",
]

for rel in BROKER_DIST_PATHS:
    full = DIST_BACKEND / rel
    if full.exists():
        ok(f"Exists in dist: {rel}")
    else:
        fail(f"Missing from dist: {full.relative_to(REPO)}")

# Check /api/kit in backend_router_registry.py
registry_file = DIST_BACKEND / "app" / "core" / "backend_router_registry.py"
if not registry_file.exists():
    fail(f"backend_router_registry.py not found in dist")
else:
    registry_text = registry_file.read_text(encoding="utf-8")
    if "routes_kit_broker" in registry_text:
        ok("routes_kit_broker registered in dist backend_router_registry.py")
    else:
        fail("routes_kit_broker NOT found in dist backend_router_registry.py")


# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} failure(s)")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: All tests passed")
    sys.exit(0)
