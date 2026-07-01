param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$SystemDirectory = "dist\generated-system",
    [string]$DbPlanPath = "assembly\db-plan\db-assembly-plan.json"
)

$ErrorActionPreference = "Stop"

function Read-JsonUtf8([string]$Path) {
    return Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
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

from sqlalchemy import select

from app.core.database import Base, close_db, init_db


def load_bootstrap_plan() -> dict[str, object]:
    current = Path(__file__).resolve()
    for parent in current.parents:
        plan_path = parent / "db-bootstrap-plan.json"
        if plan_path.exists():
            return json.loads(plan_path.read_text(encoding="utf-8-sig"))
    return {}


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


def _schema_columns(schema_json: dict[str, object]) -> list[str]:
    fields = schema_json.get("fields") or schema_json.get("columns") or []
    columns: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        column = field.get("fieldKey") or field.get("name")
        if column:
            columns.append(str(column))
    return columns


_META_COLS: list[tuple[str, str]] = [
    ('"_tenant_id"',     "UUID"),
    ('"_import_job_id"', "UUID"),
    ('"_row_index"',     "INTEGER"),
    ('"_imported_at"',   "TIMESTAMPTZ DEFAULT NOW()"),
]


def create_schema_target_tables(connection, schema_versions: list[dict[str, object]]) -> int:
    created = 0
    for version in schema_versions:
        table_code = version.get("formCode") or version.get("tableCode")
        if not isinstance(table_code, str) or not table_code.startswith("daihui_"):
            continue
        schema_json = version.get("schemaJson") or {}
        if not isinstance(schema_json, dict):
            continue
        columns = [c for c in _schema_columns(schema_json) if c.replace("_", "").isalnum()]
        if not columns:
            continue
        biz_sql  = ", ".join(f'"{c}" TEXT' for c in columns)
        meta_sql = ", ".join(f"{col} {typ}" for col, typ in _META_COLS)
        connection.execute(text(
            f'CREATE TABLE IF NOT EXISTS "{table_code}" ({biz_sql}, {meta_sql})'
        ))
        for col, typ in _META_COLS:
            connection.execute(text(
                f'ALTER TABLE "{table_code}" ADD COLUMN IF NOT EXISTS {col} {typ}'
            ))
        safe = table_code.replace('"', '')
        connection.execute(text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{safe}_job_row" '
            f'ON "{table_code}" ("_tenant_id", "_import_job_id", "_row_index")'
        ))
        created += 1
    return created


def seed_schema_contracts(connection) -> dict[str, int]:
    plan = load_bootstrap_plan()
    schema_contract = plan.get("schemaContract") or {}
    seed_data = schema_contract.get("seedData") or {}
    form_definitions = seed_data.get("formDefinitions") or []
    schema_versions = seed_data.get("schemaVersions") or []

    table_registry = Base.metadata.tables.get("table_registry")
    schema_versions_table = Base.metadata.tables.get("schema_versions")
    tenants_table = Base.metadata.tables.get("tenants")
    stations_table = Base.metadata.tables.get("stations")
    station_schemas_table = Base.metadata.tables.get("station_schemas")

    if table_registry is None or schema_versions_table is None:
        return {
            "seededFormDefinitions": 0,
            "seededSchemaVersions": 0,
            "seededStations": 0,
            "seededStationSchemas": 0,
        }

    table_ids: dict[str, object] = {}
    seeded_forms = 0

    for form in form_definitions:
        table_code = form.get("tableCode") or form.get("formCode")
        if not table_code:
            continue

        existing_id = connection.execute(
            select(table_registry.c.id).where(table_registry.c.table_code == table_code)
        ).scalar_one_or_none()

        if existing_id is None:
            result = connection.execute(
                table_registry.insert().values(
                    table_code=table_code,
                    display_name=form.get("displayName") or table_code,
                )
            )
            existing_id = result.inserted_primary_key[0]
            seeded_forms += 1

        table_ids[table_code] = existing_id

    seeded_versions = 0
    for version in schema_versions:
        table_code = version.get("formCode") or version.get("tableCode")
        schema_hash = version.get("schemaHash")
        if not table_code or not schema_hash:
            continue

        table_id = table_ids.get(table_code)
        if table_id is None:
            table_id = connection.execute(
                select(table_registry.c.id).where(table_registry.c.table_code == table_code)
            ).scalar_one_or_none()
        if table_id is None:
            continue

        existing_version_id = connection.execute(
            select(schema_versions_table.c.id).where(
                schema_versions_table.c.table_id == table_id,
                schema_versions_table.c.schema_hash == schema_hash,
            )
        ).scalar_one_or_none()

        if existing_version_id is not None:
            continue

        connection.execute(
            schema_versions_table.insert().values(
                table_id=table_id,
                schema_hash=schema_hash,
                header_fingerprint=version.get("headerFingerprint") or "",
                schema_json=version.get("schemaJson") or {},
            )
        )
        seeded_versions += 1

    seeded_stations = 0
    seeded_station_schemas = 0
    if tenants_table is not None and stations_table is not None and station_schemas_table is not None:
        tenant_ids = connection.execute(select(tenants_table.c.id)).scalars().all()
        versions_by_code = {
            version.get("formCode") or version.get("tableCode"): version
            for version in schema_versions
            if version.get("formCode") or version.get("tableCode")
        }
        for tenant_id in tenant_ids:
            for sort_order, form in enumerate(form_definitions):
                table_code = form.get("tableCode") or form.get("formCode")
                if not table_code:
                    continue
                station_id = connection.execute(
                    select(stations_table.c.id).where(
                        stations_table.c.tenant_id == tenant_id,
                        stations_table.c.code == table_code,
                    )
                ).scalar_one_or_none()
                if station_id is None:
                    result = connection.execute(
                        stations_table.insert().values(
                            tenant_id=tenant_id,
                            code=table_code,
                            name=form.get("displayName") or table_code,
                            sort_order=sort_order,
                            has_items=False,
                        )
                    )
                    station_id = result.inserted_primary_key[0]
                    seeded_stations += 1

                version = versions_by_code.get(table_code) or {}
                schema_json = version.get("schemaJson") or {}
                fields = schema_json.get("fields") or []
                unique_key_fields = [
                    field.get("fieldKey")
                    for field in fields
                    if field.get("fieldKey") and field.get("role") in {"lot", "material", "quality_result"}
                ]
                if not unique_key_fields:
                    unique_key_fields = [
                        field.get("fieldKey")
                        for field in fields
                        if field.get("fieldKey") and bool(field.get("is_key"))
                    ]
                existing_schema_id = connection.execute(
                    select(station_schemas_table.c.id).where(
                        station_schemas_table.c.station_id == station_id,
                        station_schemas_table.c.version == int(version.get("version") or 1),
                    )
                ).scalar_one_or_none()
                if existing_schema_id is None:
                    connection.execute(
                        station_schemas_table.insert().values(
                            station_id=station_id,
                            version=int(version.get("version") or 1),
                            is_active=True,
                            record_fields=fields,
                            item_fields=None,
                            unique_key_fields=unique_key_fields,
                            csv_signature_columns=[
                                field.get("sourceName")
                                for field in fields
                                if field.get("sourceName")
                            ],
                            csv_filename_pattern=None,
                            csv_field_mapping=schema_json,
                        )
                    )
                    seeded_station_schemas += 1

    created_schema_tables = create_schema_target_tables(connection, schema_versions)

    return {
        "seededFormDefinitions": seeded_forms,
        "seededSchemaVersions": seeded_versions,
        "seededStations": seeded_stations,
        "seededStationSchemas": seeded_station_schemas,
        "createdSchemaTargetTables": created_schema_tables,
    }


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
            seed_result = await connection.run_sync(seed_schema_contracts)
    finally:
        await close_db()

    result["created"] = True
    result.update(seed_result)
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
        "Seed table_registry and schema_versions from db-bootstrap-plan.json when schema seed data exists.",
        "Run scripts\check-db.ps1 without -Connect for structural validation.",
        "Run scripts\check-db.ps1 -Connect to verify an actual database connection."
    )
}

$bootstrapPlan["schemaContract"] = [ordered]@{
    tables = $plan.tables
    relationships = $plan.relationships
    indexes = $plan.indexes
    schemaVersions = $plan.schemaVersions
    seedData = $plan.seedData
    sourceSamples = $plan.sourceSamples
    schemaContracts = $plan.schemaContracts
}

$bootstrapPlan | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 (Join-Path $systemRoot "db-bootstrap-plan.json")

Write-Host "Generated DB bootstrap files in $systemRoot"
