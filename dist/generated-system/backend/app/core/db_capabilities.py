from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def list_forms(db: AsyncSession, tenant_id: Any | None = None, **_: Any) -> list[dict[str, Any]]:
    try:
        from app.models.station import Station, StationSchema
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="forms DB capability is not installed") from exc

    stmt = select(Station).order_by(Station.sort_order, Station.code)
    if tenant_id is not None and hasattr(Station, "tenant_id"):
        stmt = stmt.where(Station.tenant_id == tenant_id)
    stations = (await db.execute(stmt)).scalars().all()
    result: list[dict[str, Any]] = []
    for station in stations:
        schema = (
            await db.execute(
                select(StationSchema)
                .where(StationSchema.station_id == station.id, StationSchema.is_active == True)
                .order_by(StationSchema.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        result.append(
            {
                "id": str(station.id),
                "code": station.code,
                "name": station.name,
                "sort_order": station.sort_order,
                "schema_version": schema.version if schema else None,
                "fields": schema.record_fields if schema else None,
            }
        )
    return result


async def resolve_table(db: AsyncSession, table_code: str | None = None, **_: Any) -> dict[str, Any] | None:
    if not table_code:
        raise HTTPException(status_code=422, detail="table_code is required")
    try:
        from app.models.core.schema_registry import SchemaVersion, TableRegistry
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="table registry DB capability is not installed") from exc

    table = (
        await db.execute(select(TableRegistry).where(TableRegistry.table_code == table_code))
    ).scalar_one_or_none()
    if not table:
        return None
    schema = (
        await db.execute(
            select(SchemaVersion)
            .where(SchemaVersion.table_id == table.id)
            .order_by(SchemaVersion.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "id": str(table.id),
        "table_code": table.table_code,
        "display_name": table.display_name,
        "schema": schema.schema_json if schema else None,
    }


async def search_records(
    db: AsyncSession,
    tenant_id: Any | None = None,
    station_id: str | None = None,
    limit: int = 50,
    **_: Any,
) -> list[dict[str, Any]]:
    try:
        from app.models.generic_record import GenericRecord
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="generic record DB capability is not installed") from exc

    stmt = select(GenericRecord).order_by(GenericRecord.created_at.desc()).limit(min(max(int(limit), 1), 200))
    if tenant_id is not None:
        stmt = stmt.where(GenericRecord.tenant_id == tenant_id)
    if station_id:
        stmt = stmt.where(GenericRecord.station_id == station_id)
    records = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(record.id),
            "tenant_id": str(record.tenant_id),
            "station_id": str(record.station_id),
            "lot_no_raw": record.lot_no_raw,
            "data": record.data,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
        for record in records
    ]


DB_CAPABILITIES = {
    "db.forms.list": list_forms,
    "db.tables.resolve": resolve_table,
    "db.records.search": search_records,
}
