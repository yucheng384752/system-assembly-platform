"""Station administration API."""
from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.models.core.tenant import Tenant
from app.models.generic_record import GenericRecord
from app.models.station import Station, StationLink, StationSchema

router = APIRouter(tags=["Stations"])


class StationCreate(BaseModel):
    code: str
    name: str
    sort_order: int = 0
    has_items: bool = False


class StationUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


class StationRead(BaseModel):
    id: str
    code: str
    name: str
    sort_order: int
    has_items: bool
    record_count: int = 0


def _normalize_code(code: str) -> str:
    return code.strip().upper()


def _to_station_read(station: Station, record_count: int = 0) -> StationRead:
    return StationRead(
        id=str(station.id),
        code=station.code,
        name=station.name,
        sort_order=station.sort_order,
        has_items=station.has_items,
        record_count=record_count,
    )


async def _get_station(code: str, tenant_id: uuid.UUID, db: AsyncSession) -> Station:
    station = (
        await db.execute(
            select(Station).where(
                Station.tenant_id == tenant_id,
                Station.code == _normalize_code(code),
            )
        )
    ).scalar_one_or_none()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station '{code}' not found")
    return station


async def _active_schema(station_id: uuid.UUID, db: AsyncSession) -> StationSchema | None:
    return (
        await db.execute(
            select(StationSchema)
            .where(StationSchema.station_id == station_id, StationSchema.is_active == True)
            .order_by(StationSchema.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


@router.get("/stations", response_model=list[StationRead])
async def list_stations(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    counts = (
        select(
            GenericRecord.station_id.label("station_id"),
            func.count(GenericRecord.id).label("record_count"),
        )
        .where(GenericRecord.tenant_id == tenant.id)
        .group_by(GenericRecord.station_id)
        .subquery()
    )

    rows = (
        await db.execute(
            select(
                Station,
                func.coalesce(counts.c.record_count, 0).label("record_count"),
            )
            .outerjoin(counts, counts.c.station_id == Station.id)
            .where(Station.tenant_id == tenant.id)
            .order_by(Station.sort_order, Station.code)
        )
    ).all()
    return [_to_station_read(station, int(record_count or 0)) for station, record_count in rows]


@router.post("/stations", response_model=StationRead, status_code=status.HTTP_201_CREATED)
async def create_station(
    body: StationCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    code = _normalize_code(body.code)
    if not code:
        raise HTTPException(status_code=422, detail="code is required")

    existing = (
        await db.execute(
            select(Station.id).where(Station.tenant_id == tenant.id, Station.code == code)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Station code '{code}' already exists")

    station = Station(
        tenant_id=tenant.id,
        code=code,
        name=body.name.strip() or code,
        sort_order=body.sort_order,
        has_items=body.has_items,
    )
    db.add(station)
    await db.commit()
    await db.refresh(station)
    return _to_station_read(station)


@router.put("/stations/{code}", response_model=StationRead)
async def update_station(
    code: str,
    body: StationUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    station = await _get_station(code, tenant.id, db)
    if body.name is not None:
        station.name = body.name.strip() or station.code
    if body.sort_order is not None:
        station.sort_order = body.sort_order
    await db.commit()
    await db.refresh(station)

    record_count = (
        await db.execute(
            select(func.count(GenericRecord.id)).where(
                GenericRecord.tenant_id == tenant.id,
                GenericRecord.station_id == station.id,
            )
        )
    ).scalar() or 0
    return _to_station_read(station, int(record_count))


@router.delete("/stations/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_station(
    code: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    station = await _get_station(code, tenant.id, db)
    await db.execute(
        sql_delete(GenericRecord).where(
            GenericRecord.tenant_id == tenant.id,
            GenericRecord.station_id == station.id,
        )
    )
    await db.execute(
        sql_delete(StationLink).where(
            StationLink.tenant_id == tenant.id,
            or_(
                StationLink.from_station_id == station.id,
                StationLink.to_station_id == station.id,
            ),
        )
    )
    await db.execute(sql_delete(StationSchema).where(StationSchema.station_id == station.id))
    await db.execute(sql_delete(Station).where(Station.id == station.id))
    await db.commit()


@router.get("/stations/{code}/export")
async def export_station_records(
    code: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    station = await _get_station(code, tenant.id, db)
    schema = await _active_schema(station.id, db)
    if not schema:
        raise HTTPException(status_code=404, detail="Active station schema not found")

    fields = schema.record_fields or []
    field_names = [field["name"] for field in fields if field.get("name")]
    if not field_names:
        raise HTTPException(status_code=422, detail="Active station schema has no record fields")

    records = (
        await db.execute(
            select(GenericRecord)
            .where(
                GenericRecord.tenant_id == tenant.id,
                GenericRecord.station_id == station.id,
            )
            .order_by(GenericRecord.created_at)
        )
    ).scalars().all()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=field_names, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow({name: (record.data or {}).get(name) for name in field_names})

    filename = f"{station.code.lower()}-records.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
