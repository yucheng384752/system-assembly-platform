param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$SystemDirectory = "dist\generated-system",
    [string]$DbPlanPath = "assembly\db-plan\db-assembly-plan.json",
    [string]$BaselinePath = (Join-Path $PSScriptRoot "..\assembly\baselines\default-db-schema.baseline.json")
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
}

# Load DB schema baseline if available
$schemaContract = $null
if (Test-Path $BaselinePath) {
    $schemaBaseline = Read-JsonUtf8 $BaselinePath
    $schemaContract = [ordered]@{
        baselineFile = (Resolve-Path $BaselinePath).Path
        tables = $schemaBaseline.tables
    }
}

$systemRoot = Join-Path $ProjectRoot $SystemDirectory
$backendRoot = Join-Path $systemRoot "backend"
$coreRoot = Join-Path $backendRoot "app\core"
$scriptsRoot = Join-Path $systemRoot "scripts"
$plan = Read-JsonUtf8 (Join-Path $ProjectRoot $DbPlanPath)

if (-not (Test-Path (Join-Path $coreRoot "database.py"))) {
    throw "Generated backend database module is missing: backend\app\core\database.py"
}

New-Item -ItemType Directory -Force $coreRoot | Out-Null
New-Item -ItemType Directory -Force $scriptsRoot | Out-Null

$bootstrapPython = @'
"""Generated database bootstrap entrypoint.

This module registers available SQLAlchemy models and creates tables through
the selected backend database module. It is used by scripts/migrate.ps1 when
Alembic migrations are not present in the assembled system.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
from pathlib import Path

from app.core.database import Base, close_db, init_db


def import_model_modules() -> list[str]:
    app_root = Path(__file__).resolve().parents[1]
    models_root = app_root / "models"
    imported: list[str] = []

    if not models_root.exists():
        return imported

    for model_file in sorted(models_root.rglob("*.py")):
        if model_file.name == "__init__.py":
            continue

        module_name = "app." + ".".join(model_file.relative_to(app_root).with_suffix("").parts)
        importlib.import_module(module_name)
        imported.append(module_name)

    return imported


async def bootstrap(check_only: bool = False) -> dict[str, object]:
    imported_modules = import_model_modules()
    tables = sorted(Base.metadata.tables.keys())

    result: dict[str, object] = {
        "importedModelModules": imported_modules,
        "tableCount": len(tables),
        "tables": tables,
        "checkOnly": check_only,
    }

    if check_only:
        return result

    await init_db()
    try:
        from app.core import database

        if database.engine is None:
            raise RuntimeError("Database engine was not initialized.")

        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await close_db()

    result["created"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap generated database tables.")
    parser.add_argument("--check", action="store_true", help="Only import models and report metadata.")
    args = parser.parse_args()

    result = asyncio.run(bootstrap(check_only=args.check))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
'@

$bootstrapPython | Set-Content -Encoding UTF8 (Join-Path $coreRoot "generated_db_bootstrap.py")

$checkDbScript = @'
param(
    [string]$Python = "python",
    [switch]$Connect
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$BackendRoot = Join-Path $Root "backend"
$BootstrapPath = Join-Path $BackendRoot "app\core\generated_db_bootstrap.py"
$EnvPath = Join-Path $Root ".env"
$EnvExamplePath = Join-Path $Root ".env.example"

if (-not (Test-Path $BootstrapPath)) {
    throw "Database bootstrap module is missing: backend\app\core\generated_db_bootstrap.py"
}

if (-not (Test-Path $EnvPath) -and (Test-Path $EnvExamplePath)) {
    Copy-Item -LiteralPath $EnvExamplePath -Destination $EnvPath
    Write-Host "Created .env from .env.example"
}

$summary = [ordered]@{
    root = $Root
    bootstrapModule = "backend\app\core\generated_db_bootstrap.py"
    envPresent = Test-Path $EnvPath
    connectRequested = [bool]$Connect
}
$summary | ConvertTo-Json -Depth 10

if ($Connect) {
    Push-Location $BackendRoot
    try {
        & $Python -m app.core.generated_db_bootstrap
    } finally {
        Pop-Location
    }
}
'@

$checkDbScript | Set-Content -Encoding UTF8 (Join-Path $scriptsRoot "check-db.ps1")

$bootstrapPlan = [ordered]@{
    generatedAt = (Get-Date).ToString("s")
    sourcePlan = $DbPlanPath
    engine = $plan.engine
    connectionOwner = $plan.connectionOwner
    envVars = $plan.envVars
    migrations = $plan.migrations
    scripts = [ordered]@{
        bootstrapModule = "backend\app\core\generated_db_bootstrap.py"
        checkScript = "scripts\check-db.ps1"
        migrateScript = "scripts\migrate.ps1"
    }
    behavior = @(
        "Import available backend model modules.",
        "Use Alembic when backend\alembic.ini exists.",
        "Use SQLAlchemy metadata create_all when Alembic is not present.",
        "Run scripts\check-db.ps1 without -Connect for structural validation.",
        "Run scripts\check-db.ps1 -Connect to verify an actual database connection."
    )
}

if ($null -ne $schemaContract) {
    $bootstrapPlan["schemaContract"] = $schemaContract
}

$bootstrapPlan | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $systemRoot "db-bootstrap-plan.json")

Write-Host "Generated DB bootstrap files in $systemRoot"
