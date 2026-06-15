"""Analytics mapping administration API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.models.analytics_mapping import AnalyticsMapping
from app.models.core.tenant import Tenant
from app.models.station import Station

router = APIRouter(tags=["Analytics Mappings"])


class AnalyticsMappingCreate(BaseModel):
    station_id: uuid.UUID
    source_path: str
    output_column: str
    output_order: int
    data_type: str = "string"
    null_if_missing: bool = True


class AnalyticsMappingUpdate(BaseModel):
    output_order: int | None = None
    data_type: str | None = None
    null_if_missing: bool | None = None


class AnalyticsMappingRead(BaseModel):
    id: str
    station_id: str
    source_path: str
    output_column: str
    output_order: int
    data_type: str
    null_if_missing: bool


def _to_mapping_read(mapping: AnalyticsMapping) -> AnalyticsMappingRead:
    return AnalyticsMappingRead(
        id=str(mapping.id),
        station_id=str(mapping.station_id),
        source_path=mapping.source_path,
        output_column=mapping.output_column,
        output_order=mapping.output_order,
        data_type=mapping.data_type,
        null_if_missing=mapping.null_if_missing,
    )


async def _ensure_station(tenant_id: uuid.UUID, station_id: uuid.UUID, db: AsyncSession) -> None:
    exists = (
        await db.execute(
            select(Station.id).where(
                Station.tenant_id == tenant_id,
                Station.id == station_id,
            )
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Station not found")


async def _get_mapping(
    mapping_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> AnalyticsMapping:
    mapping = (
        await db.execute(
            select(AnalyticsMapping).where(
                AnalyticsMapping.tenant_id == tenant_id,
                AnalyticsMapping.id == mapping_id,
            )
        )
    ).scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Analytics mapping not found")
    return mapping


@router.get("/analytics-mappings", response_model=list[AnalyticsMappingRead])
async def list_analytics_mappings(
    station_id: uuid.UUID | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AnalyticsMapping).where(AnalyticsMapping.tenant_id == tenant.id)
    if station_id is not None:
        stmt = stmt.where(AnalyticsMapping.station_id == station_id)
    rows = (
        await db.execute(
            stmt.order_by(AnalyticsMapping.output_order, AnalyticsMapping.output_column)
        )
    ).scalars().all()
    return [_to_mapping_read(mapping) for mapping in rows]


@router.post(
    "/analytics-mappings",
    response_model=AnalyticsMappingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_analytics_mapping(
    body: AnalyticsMappingCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_station(tenant.id, body.station_id, db)

    existing = (
        await db.execute(
            select(AnalyticsMapping.id).where(
                AnalyticsMapping.tenant_id == tenant.id,
                AnalyticsMapping.station_id == body.station_id,
                AnalyticsMapping.output_column == body.output_column,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Analytics mapping already exists")

    mapping = AnalyticsMapping(
        tenant_id=tenant.id,
        station_id=body.station_id,
        source_path=body.source_path.strip(),
        output_column=body.output_column.strip(),
        output_order=body.output_order,
        data_type=body.data_type.strip(),
        null_if_missing=body.null_if_missing,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return _to_mapping_read(mapping)


@router.put("/analytics-mappings/{mapping_id}", response_model=AnalyticsMappingRead)
async def update_analytics_mapping(
    mapping_id: uuid.UUID,
    body: AnalyticsMappingUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    mapping = await _get_mapping(mapping_id, tenant.id, db)
    if body.output_order is not None:
        mapping.output_order = body.output_order
    if body.data_type is not None:
        mapping.data_type = body.data_type.strip()
    if body.null_if_missing is not None:
        mapping.null_if_missing = body.null_if_missing
    await db.commit()
    await db.refresh(mapping)
    return _to_mapping_read(mapping)


@router.delete("/analytics-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analytics_mapping(
    mapping_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    deleted = await db.execute(
        sql_delete(AnalyticsMapping).where(
            AnalyticsMapping.tenant_id == tenant.id,
            AnalyticsMapping.id == mapping_id,
        )
    )
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="Analytics mapping not found")
    await db.commit()
