"""Delete all test import data from VM DB."""
import asyncio

async def main():
    import asyncpg
    conn = await asyncpg.connect("postgresql://form_system:qqq123@localhost:5432/form_system")

    steps = [
        ("staging_rows",     "DELETE FROM staging_rows"),
        ("import_files",     "DELETE FROM import_files"),
        ("import_jobs",      "DELETE FROM import_jobs"),
        ("upload_jobs",      "DELETE FROM upload_jobs"),
        ("generic_records",  "DELETE FROM generic_records"),
        ("daihui_entry",     "DELETE FROM daihui_entry"),
        ("daihui_inspection","DELETE FROM daihui_inspection"),
        ("daihui_material",  "DELETE FROM daihui_material"),
        ("daihui_production","DELETE FROM daihui_production"),
        ("daihui_quality",   "DELETE FROM daihui_quality"),
    ]

    for name, sql in steps:
        result = await conn.execute(sql)
        count = result.split()[-1]
        print(f"DELETE {name}: {count} rows deleted")

    tables = [
        "daihui_entry", "daihui_inspection", "daihui_material",
        "daihui_production", "daihui_quality", "generic_records",
        "import_jobs", "import_files", "staging_rows", "upload_jobs",
    ]
    print("\n--- Final row counts ---")
    for t in tables:
        cnt = await conn.fetchval(f"SELECT COUNT(*) FROM {t}")
        status = "OK " if cnt == 0 else "WARN"
        print(f"  [{status}] {t}: {cnt}")

    await conn.close()

asyncio.run(main())
