"""Station link administration API."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.models.core.tenant import Tenant
from app.models.station import Station, StationLink

router = APIRouter(tags=["Station Links"])


class StationLinkCreate(BaseModel):
    from_station_code: str
    to_station_code: str
    link_type: str
    link_config: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class StationLinkRead(BaseModel):
    id: str
    from_station_id: str
    to_station_id: str
    from_station_code: str
    to_station_code: str
    link_type: str
    link_config: dict[str, Any]
    sort_order: int


def _normalize_code(code: str) -> str:
    return code.strip().upper()


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


def _to_link_read(
    link: StationLink,
    from_station_code: str,
    to_station_code: str,
) -> StationLinkRead:
    return StationLinkRead(
        id=str(link.id),
        from_station_id=str(link.from_station_id),
        to_station_id=str(link.to_station_id),
        from_station_code=from_station_code,
        to_station_code=to_station_code,
        link_type=link.link_type,
        link_config=link.link_config,
        sort_order=link.sort_order,
    )


@router.get("/station-links", response_model=list[StationLinkRead])
async def list_station_links(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from_station = Station.__table__.alias("from_station")
    to_station = Station.__table__.alias("to_station")
    rows = (
        await db.execute(
            select(
                StationLink,
                from_station.c.code.label("from_station_code"),
                to_station.c.code.label("to_station_code"),
            )
            .join(from_station, from_station.c.id == StationLink.from_station_id)
            .join(to_station, to_station.c.id == StationLink.to_station_id)
            .where(StationLink.tenant_id == tenant.id)
            .order_by(StationLink.sort_order, from_station.c.code, to_station.c.code)
        )
    ).all()
    return [
        _to_link_read(link, from_station_code, to_station_code)
        for link, from_station_code, to_station_code in rows
    ]


@router.post(
    "/station-links",
    response_model=StationLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_station_link(
    body: StationLinkCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from_station = await _get_station(body.from_station_code, tenant.id, db)
    to_station = await _get_station(body.to_station_code, tenant.id, db)
    if from_station.id == to_station.id:
        raise HTTPException(status_code=422, detail="from_station_code and to_station_code must differ")

    existing = (
        await db.execute(
            select(StationLink.id).where(
                StationLink.tenant_id == tenant.id,
                StationLink.from_station_id == from_station.id,
                StationLink.to_station_id == to_station.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Station link already exists")

    link = StationLink(
        tenant_id=tenant.id,
        from_station_id=from_station.id,
        to_station_id=to_station.id,
        link_type=body.link_type.strip(),
        link_config=body.link_config,
        sort_order=body.sort_order,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return _to_link_read(link, from_station.code, to_station.code)


@router.delete("/station-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_station_link(
    link_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    deleted = await db.execute(
        sql_delete(StationLink).where(
            StationLink.tenant_id == tenant.id,
            StationLink.id == link_id,
        )
    )
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="Station link not found")
    await db.commit()
