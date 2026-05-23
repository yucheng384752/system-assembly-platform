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
    plan_path = Path(__file__).resolve().parents[3] / "db-bootstrap-plan.json"
    if not plan_path.exists():
        return {}
    return json.loads(plan_path.read_text(encoding="utf-8"))


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


def seed_schema_contracts(connection) -> dict[str, int]:
    plan = load_bootstrap_plan()
    schema_contract = plan.get("schemaContract") or {}
    seed_data = schema_contract.get("seedData") or {}
    form_definitions = seed_data.get("formDefinitions") or []
    schema_versions = seed_data.get("schemaVersions") or []

    table_registry = Base.metadata.tables.get("table_registry")
    schema_versions_table = Base.metadata.tables.get("schema_versions")

    if table_registry is None or schema_versions_table is None:
        return {
            "seededFormDefinitions": 0,
            "seededSchemaVersions": 0,
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

    return {
        "seededFormDefinitions": seeded_forms,
        "seededSchemaVersions": seeded_versions,
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
