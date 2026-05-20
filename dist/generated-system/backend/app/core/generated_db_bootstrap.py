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
